using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace ArkestratorBridge
{
    [InitializeOnLoad]
    public static class ArkestratorBridge
    {
        private const string Program = "unity";
        private const string BridgeVersion = "1.0.0";
        private const int ProtocolVersion = 1;
        private const string DefaultWsUrl = "ws://localhost:7800/ws";
        private const double ContextPushIntervalSeconds = 3.0;
        private const long MaxAttachmentBytes = 1024 * 1024;
        private const string AddCurrentSelectionMenuPath = "Arkestrator/Add Current Selection to Arkestrator Context";
        private const string AssetsAddToContextMenuPath = "Assets/Add to Arkestrator Context";
        private const string GameObjectAddToContextMenuPath = "GameObject/Add to Arkestrator Context";
        private const string ComponentContextMenuPath = "CONTEXT/Component/Add to Arkestrator Context";
        private const string TransformContextMenuPath = "CONTEXT/Transform/Add to Arkestrator Context";

        private static ArkestratorWebSocketClient? _ws;
        private static bool _initialized;
        private static double _lastContextPushTime;
        private static string _lastContextHash = string.Empty;
        private static int _nextContextIndex = 1;
        private static string _lastSharedApiKey = string.Empty;
        private static string _lastSharedWsUrl = string.Empty;
        private static string _lastSharedWorkerName = string.Empty;
        private static string _lastSharedMachineId = string.Empty;
        private static bool _followSharedWsUrl = true;
        private static string _lastConnectedFullUrl = string.Empty;

        static ArkestratorBridge()
        {
            Initialize();
        }

        private static void Initialize()
        {
            if (_initialized)
            {
                return;
            }

            _initialized = true;

            _ws = new ArkestratorWebSocketClient
            {
                OnConnected = OnConnected,
                OnDisconnected = OnDisconnected,
                OnError = OnError,
                OnMessage = OnMessage,
            };

            EditorApplication.update += OnEditorUpdate;
            AssemblyReloadEvents.beforeAssemblyReload += Shutdown;
            EditorApplication.quitting += Shutdown;
            EditorApplication.delayCall += AutoConnect;
        }

        [MenuItem("Arkestrator/Connect", priority = 10)]
        private static void ConnectMenu()
        {
            var config = ReadSharedConfig();
            if (config == null || string.IsNullOrWhiteSpace(config.EffectiveApiKey))
            {
                Debug.LogWarning("[ArkestratorBridge] Missing ~/.arkestrator/config.json apiKey; log in with the Arkestrator client first.");
                return;
            }

            Connect(config);
        }

        [MenuItem("Arkestrator/Disconnect", priority = 11)]
        private static void DisconnectMenu()
        {
            _ws?.Disconnect();
            Debug.Log("[ArkestratorBridge] Disconnect requested.");
        }

        [MenuItem("Arkestrator/Push Editor Context Now", priority = 20)]
        private static void PushEditorContextNowMenu()
        {
            PushEditorContext(force: true);
        }

        [MenuItem(AddCurrentSelectionMenuPath, true, 21)]
        private static bool ValidateAddCurrentSelectionToContext()
        {
            return _ws is { Connected: true } && HasAnySelection();
        }

        [MenuItem(AddCurrentSelectionMenuPath, false, 21)]
        private static void AddCurrentSelectionToContext()
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            AddSelectedAssetsToContext();
            AddSelectedObjectsToContext();
        }

        [MenuItem(AssetsAddToContextMenuPath, true)]
        private static bool ValidateAddSelectedAssetsToContext()
        {
            return _ws is { Connected: true } && Selection.assetGUIDs.Length > 0;
        }

        [MenuItem(AssetsAddToContextMenuPath, false, 2000)]
        private static void AddSelectedAssetsToContext()
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            foreach (var guid in Selection.assetGUIDs)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrWhiteSpace(path))
                {
                    continue;
                }

                var type = DetectContextItemType(path);
                var item = new Dictionary<string, object?>
                {
                    ["index"] = _nextContextIndex++,
                    ["type"] = type,
                    ["name"] = Path.GetFileName(path),
                    ["path"] = path,
                };

                if (IsTextAsset(path) && TryReadTextAsset(path, out var content))
                {
                    item["content"] = content;
                }

                item["metadata"] = new Dictionary<string, object?>
                {
                    ["asset_path"] = path,
                    ["unity_type"] = AssetDatabase.GetMainAssetTypeAtPath(path)?.Name ?? "Unknown",
                };

                SendEnvelope("bridge_context_item_add", new Dictionary<string, object?>
                {
                    ["item"] = item,
                });
            }
        }

        [MenuItem(GameObjectAddToContextMenuPath, true)]
        private static bool ValidateAddSelectedObjectsToContext()
        {
            return _ws is { Connected: true } && Selection.gameObjects.Length > 0;
        }

        [MenuItem(GameObjectAddToContextMenuPath, false, 49)]
        private static void AddSelectedObjectsToContext()
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            foreach (var go in Selection.gameObjects)
            {
                AddGameObjectToContext(go);
            }
        }

        [MenuItem(ComponentContextMenuPath, false, 2099)]
        private static void AddComponentContextToContext(MenuCommand command)
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            var component = command.context as Component;
            if (component == null)
            {
                return;
            }

            AddGameObjectToContext(component.gameObject);
        }

        [MenuItem(TransformContextMenuPath, false, 2100)]
        private static void AddTransformContextToContext(MenuCommand command)
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            var transform = command.context as Transform;
            if (transform == null)
            {
                return;
            }

            AddGameObjectToContext(transform.gameObject);
        }

        private static void AutoConnect()
        {
            var config = ReadSharedConfig();
            if (config == null || string.IsNullOrWhiteSpace(config.EffectiveApiKey))
            {
                return;
            }

            Connect(config);
        }

        private static void Connect(SharedConfig config)
        {
            var wsUrl = ResolveWsUrl(config);
            var apiKey = config.EffectiveApiKey;
            var workerName = config.EffectiveWorkerName;
            var machineId = config.EffectiveMachineId;
            _followSharedWsUrl = IsLoopbackWsUrl(wsUrl);
            _lastSharedApiKey = apiKey;
            _lastSharedWsUrl = config.EffectiveWsUrl;
            _lastSharedWorkerName = workerName;
            _lastSharedMachineId = machineId;
            Connect(wsUrl, apiKey, workerName, machineId);
        }

        private static void Connect(string wsUrl, string apiKey, string workerName = "", string machineId = "")
        {
            if (_ws == null)
            {
                Initialize();
            }

            if (_ws == null)
            {
                return;
            }

            var fullUrl = BuildConnectionUrl(wsUrl, apiKey, workerName, machineId);
            if (_ws.Connected && string.Equals(_lastConnectedFullUrl, fullUrl, StringComparison.Ordinal))
            {
                return;
            }

            _lastConnectedFullUrl = fullUrl;
            _ws.Connect(fullUrl);
            Debug.Log($"[ArkestratorBridge] Connecting to {wsUrl} ...");
        }

        private static bool HasAnySelection()
        {
            return Selection.assetGUIDs.Length > 0 || Selection.gameObjects.Length > 0;
        }

        private static void AddGameObjectToContext(GameObject go)
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            var item = new Dictionary<string, object?>
            {
                ["index"] = _nextContextIndex++,
                ["type"] = "node",
                ["name"] = go.name,
                ["path"] = GetHierarchyPath(go.transform),
                ["metadata"] = new Dictionary<string, object?>
                {
                    ["class"] = go.GetType().Name,
                    ["active"] = go.activeSelf,
                    ["tag"] = go.tag,
                    ["layer"] = go.layer,
                    ["position"] = new List<object?>
                    {
                        go.transform.position.x,
                        go.transform.position.y,
                        go.transform.position.z,
                    },
                },
            };

            SendEnvelope("bridge_context_item_add", new Dictionary<string, object?>
            {
                ["item"] = item,
            });
        }

        private static string BuildConnectionUrl(string baseUrl, string apiKey, string workerName, string machineId)
        {
            var separator = baseUrl.Contains("?") ? "&" : "?";
            var query = new Dictionary<string, string>
            {
                ["type"] = "bridge",
                ["program"] = Program,
                ["bridgeVersion"] = BridgeVersion,
                ["protocolVersion"] = ProtocolVersion.ToString(),
                ["projectPath"] = GetProjectRoot(),
                ["name"] = GetProjectName(),
                ["programVersion"] = Application.unityVersion,
                ["osUser"] = Environment.UserName,
            };
            if (!string.IsNullOrWhiteSpace(workerName))
            {
                query["workerName"] = workerName;
            }
            if (!string.IsNullOrWhiteSpace(machineId))
            {
                query["machineId"] = machineId;
            }
            if (!string.IsNullOrWhiteSpace(apiKey))
            {
                query["key"] = apiKey;
            }

            var encoded = string.Join("&", query.Select(kv =>
                $"{Uri.EscapeDataString(kv.Key)}={Uri.EscapeDataString(kv.Value ?? string.Empty)}"));
            return baseUrl + separator + encoded;
        }

        private static void OnEditorUpdate()
        {
            _ws?.Poll();
            RefreshSharedConfigIfNeeded();

            if (_ws is not { Connected: true })
            {
                return;
            }

            var now = EditorApplication.timeSinceStartup;
            if (now - _lastContextPushTime < ContextPushIntervalSeconds)
            {
                return;
            }

            _lastContextPushTime = now;
            PushEditorContext(force: false);
        }

        private static void PushEditorContext(bool force)
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            var editorContext = BuildEditorContext();
            var files = GatherFileAttachments();

            var hashSource = MiniJson.Serialize(editorContext) + MiniJson.Serialize(files);
            var hash = ComputeMd5(hashSource);
            if (!force && hash == _lastContextHash)
            {
                return;
            }

            _lastContextHash = hash;
            SendEnvelope("bridge_editor_context", new Dictionary<string, object?>
            {
                ["editorContext"] = editorContext,
                ["files"] = files,
            });
        }

        private static Dictionary<string, object?> BuildEditorContext()
        {
            var activeScene = SceneManager.GetActiveScene();

            var selectedObjects = new List<object?>();
            foreach (var go in Selection.gameObjects)
            {
                selectedObjects.Add(new Dictionary<string, object?>
                {
                    ["name"] = go.name,
                    ["type"] = go.GetType().Name,
                    ["path"] = GetHierarchyPath(go.transform),
                });
            }

            var selectedAssetPaths = Selection.assetGUIDs
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Distinct()
                .Cast<object?>()
                .ToList();

            var selectedScripts = Selection.assetGUIDs
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(path => IsScriptPath(path))
                .Distinct()
                .Cast<object?>()
                .ToList();

            return new Dictionary<string, object?>
            {
                ["projectRoot"] = GetProjectRoot(),
                ["activeFile"] = string.IsNullOrEmpty(activeScene.path) ? null : activeScene.path,
                ["metadata"] = new Dictionary<string, object?>
                {
                    ["bridge_type"] = Program,
                    ["unity_version"] = Application.unityVersion,
                    ["active_scene"] = activeScene.path,
                    ["selected_objects"] = selectedObjects,
                    ["selected_assets"] = selectedAssetPaths,
                    ["selected_scripts"] = selectedScripts,
                },
            };
        }

        private static List<object?> GatherFileAttachments()
        {
            var files = new List<object?>();
            foreach (var guid in Selection.assetGUIDs)
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                if (!IsTextAsset(path))
                {
                    continue;
                }

                if (!TryReadTextAsset(path, out var content))
                {
                    continue;
                }

                files.Add(new Dictionary<string, object?>
                {
                    ["path"] = path,
                    ["content"] = content,
                });
            }

            return files;
        }

        private static void OnConnected()
        {
            Debug.Log("[ArkestratorBridge] Connected.");
            _nextContextIndex = 1;
            _lastContextHash = string.Empty;

            SendEnvelope("bridge_context_clear", new Dictionary<string, object?>());
            PushEditorContext(force: true);
        }

        private static void OnDisconnected()
        {
            Debug.Log("[ArkestratorBridge] Disconnected.");
        }

        private static void OnError(string message)
        {
            Debug.LogWarning($"[ArkestratorBridge] {message}");
        }

        private static void OnMessage(Dictionary<string, object?> message)
        {
            var type = GetString(message, "type");
            if (!message.TryGetValue("payload", out var payloadObj) || payloadObj is not Dictionary<string, object?> payload)
            {
                payload = new Dictionary<string, object?>();
            }

            switch (type)
            {
                case "job_complete":
                    HandleJobComplete(payload);
                    break;
                case "bridge_command":
                    HandleBridgeCommand(payload);
                    break;
                case "bridge_command_result":
                    HandleBridgeCommandResult(payload);
                    break;
                case "error":
                {
                    var code = GetString(payload, "code");
                    var err = GetString(payload, "message");
                    Debug.LogWarning($"[ArkestratorBridge] Error [{code}]: {err}");
                    break;
                }
            }
        }

        private static void HandleJobComplete(Dictionary<string, object?> payload)
        {
            var jobId = GetString(payload, "jobId");
            var success = GetBool(payload, "success");
            var workspaceMode = GetString(payload, "workspaceMode");
            var error = GetString(payload, "error");

            if (!string.IsNullOrWhiteSpace(error))
            {
                Debug.LogWarning($"[ArkestratorBridge] Job {jobId} failed: {error}");
            }
            else
            {
                Debug.Log($"[ArkestratorBridge] Job {jobId} completed (success={success})");
            }

            if (!success)
            {
                return;
            }

            var commands = GetList(payload, "commands");
            var files = GetList(payload, "files");

            if (workspaceMode == "command" && commands.Count > 0)
            {
                var result = ArkestratorCommandExecutor.ExecuteCommands(commands);
                Debug.Log($"[ArkestratorBridge] Commands executed={result.Executed} failed={result.Failed} skipped={result.Skipped}");
                foreach (var line in result.Errors)
                {
                    Debug.LogWarning($"[ArkestratorBridge] cmd-error: {line}");
                }
                return;
            }

            if (files.Count > 0)
            {
                var applied = ArkestratorFileApplier.ApplyFileChanges(files, GetProjectRoot());
                Debug.Log($"[ArkestratorBridge] Files applied={applied.Applied} failed={applied.Failed}");
                foreach (var line in applied.Errors)
                {
                    Debug.LogWarning($"[ArkestratorBridge] file-error: {line}");
                }

                AssetDatabase.Refresh();
            }
        }

        private static void HandleBridgeCommand(Dictionary<string, object?> payload)
        {
            var senderId = GetString(payload, "senderId");
            var correlationId = GetString(payload, "correlationId");
            var commands = GetList(payload, "commands");

            var result = ArkestratorCommandExecutor.ExecuteCommands(commands);
            Debug.Log($"[ArkestratorBridge] bridge_command from {senderId}: executed={result.Executed} failed={result.Failed}");

            SendEnvelope("bridge_command_result", new Dictionary<string, object?>
            {
                ["senderId"] = senderId,
                ["correlationId"] = correlationId,
                ["success"] = result.Failed == 0,
                ["executed"] = result.Executed,
                ["failed"] = result.Failed,
                ["skipped"] = result.Skipped,
                ["errors"] = result.Errors.Cast<object?>().ToList(),
            });
        }

        private static void HandleBridgeCommandResult(Dictionary<string, object?> payload)
        {
            var program = GetString(payload, "program");
            var success = GetBool(payload, "success");
            var executed = GetInt(payload, "executed");
            var failed = GetInt(payload, "failed");
            Debug.Log($"[ArkestratorBridge] bridge_command_result from {program}: success={success} executed={executed} failed={failed}");
        }

        private static void SendEnvelope(string type, Dictionary<string, object?> payload)
        {
            if (_ws is not { Connected: true })
            {
                return;
            }

            _ws.SendMessage(new Dictionary<string, object?>
            {
                ["type"] = type,
                ["id"] = Guid.NewGuid().ToString(),
                ["payload"] = payload,
            });
        }

        private static void Shutdown()
        {
            try
            {
                _ws?.Disconnect();
            }
            catch
            {
                // ignore
            }

            EditorApplication.update -= OnEditorUpdate;
            AssemblyReloadEvents.beforeAssemblyReload -= Shutdown;
            EditorApplication.quitting -= Shutdown;
            _initialized = false;
        }

        private static string GetProjectRoot()
        {
            return Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        }

        private static string GetProjectName()
        {
            return new DirectoryInfo(GetProjectRoot()).Name;
        }

        private static string GetHierarchyPath(Transform transform)
        {
            var names = new Stack<string>();
            var current = transform;
            while (current != null)
            {
                names.Push(current.name);
                current = current.parent;
            }
            return string.Join("/", names);
        }

        private static string ComputeMd5(string input)
        {
            using var md5 = MD5.Create();
            var bytes = md5.ComputeHash(Encoding.UTF8.GetBytes(input));
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes)
            {
                sb.Append(b.ToString("x2"));
            }
            return sb.ToString();
        }

        private static bool IsScriptPath(string path)
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext is ".cs" or ".shader" or ".hlsl" or ".cginc";
        }

        private static bool IsTextAsset(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return false;
            }

            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext is ".cs" or ".shader" or ".hlsl" or ".cginc" or ".txt" or ".json" or ".asmdef" or ".md" or ".uxml" or ".uss" or ".unity" or ".prefab";
        }

        private static bool TryReadTextAsset(string assetPath, out string content)
        {
            content = string.Empty;
            try
            {
                var fullPath = ResolveAssetPathToDisk(assetPath);
                if (!File.Exists(fullPath))
                {
                    return false;
                }

                var info = new FileInfo(fullPath);
                if (info.Length > MaxAttachmentBytes)
                {
                    return false;
                }

                content = File.ReadAllText(fullPath, Encoding.UTF8);
                return true;
            }
            catch
            {
                return false;
            }
        }

        private static string ResolveAssetPathToDisk(string assetPath)
        {
            if (Path.IsPathRooted(assetPath))
            {
                return Path.GetFullPath(assetPath);
            }

            return Path.GetFullPath(Path.Combine(GetProjectRoot(), assetPath));
        }

        private static string DetectContextItemType(string path)
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext switch
            {
                ".cs" or ".shader" or ".hlsl" or ".cginc" => "script",
                ".unity" => "scene",
                ".prefab" => "resource",
                _ => "asset",
            };
        }

        private static SharedConfig? ReadSharedConfig()
        {
            try
            {
                var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                var candidates = new[]
                {
                    Path.Combine(home, ".arkestrator", "config.json"),
                };

                var path = candidates.FirstOrDefault(File.Exists);
                if (string.IsNullOrWhiteSpace(path))
                    return null;

                var raw = File.ReadAllText(path, Encoding.UTF8);
                return JsonUtility.FromJson<SharedConfig>(raw);
            }
            catch
            {
                return null;
            }
        }

        private static string ResolveWsUrl(SharedConfig config)
        {
            if (!string.IsNullOrWhiteSpace(config.EffectiveWsUrl))
            {
                return config.EffectiveWsUrl;
            }

            if (!string.IsNullOrWhiteSpace(config.EffectiveServerUrl))
            {
                var url = config.EffectiveServerUrl.Trim();
                if (url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
                {
                    url = "wss://" + url.Substring("https://".Length);
                }
                else if (url.StartsWith("http://", StringComparison.OrdinalIgnoreCase))
                {
                    url = "ws://" + url.Substring("http://".Length);
                }
                if (!url.EndsWith("/ws", StringComparison.OrdinalIgnoreCase))
                {
                    url = url.TrimEnd('/') + "/ws";
                }

                return url;
            }

            return DefaultWsUrl;
        }

        private static bool IsLoopbackWsUrl(string url)
        {
            if (string.IsNullOrWhiteSpace(url))
            {
                return true;
            }

            if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            {
                return false;
            }

            var host = uri.Host?.Trim().ToLowerInvariant() ?? string.Empty;
            return host is "localhost" or "127.0.0.1" or "::1";
        }

        private static void RefreshSharedConfigIfNeeded()
        {
            if (_ws == null)
            {
                return;
            }

            var config = ReadSharedConfig();
            if (config == null)
            {
                return;
            }

            var newApiKey = config.EffectiveApiKey;
            var newWs = config.EffectiveWsUrl;
            var newWorkerName = config.EffectiveWorkerName;
            var newMachineId = config.EffectiveMachineId;

            var keyChanged = !string.IsNullOrWhiteSpace(newApiKey) && !string.Equals(newApiKey, _lastSharedApiKey, StringComparison.Ordinal);
            var wsChanged = _followSharedWsUrl && !string.IsNullOrWhiteSpace(newWs) && !string.Equals(newWs, _lastSharedWsUrl, StringComparison.Ordinal);
            var workerChanged = !string.Equals(newWorkerName, _lastSharedWorkerName, StringComparison.Ordinal);
            var machineChanged = !string.Equals(newMachineId, _lastSharedMachineId, StringComparison.Ordinal);
            if (!keyChanged && !wsChanged && !workerChanged && !machineChanged)
            {
                return;
            }

            _lastSharedApiKey = newApiKey;
            _lastSharedWsUrl = newWs;
            _lastSharedWorkerName = newWorkerName;
            _lastSharedMachineId = newMachineId;

            var nextWsUrl = ResolveWsUrl(config);
            _followSharedWsUrl = IsLoopbackWsUrl(nextWsUrl);
            Connect(nextWsUrl, newApiKey, newWorkerName, newMachineId);
            Debug.Log("[ArkestratorBridge] Updated shared credentials detected - reconnecting.");
        }

        private static string GetString(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value == null)
            {
                return string.Empty;
            }

            return value.ToString() ?? string.Empty;
        }

        private static bool GetBool(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value == null)
            {
                return false;
            }

            return value switch
            {
                bool b => b,
                string s => bool.TryParse(s, out var parsed) && parsed,
                long l => l != 0,
                int i => i != 0,
                double d => Math.Abs(d) > double.Epsilon,
                _ => false,
            };
        }

        private static int GetInt(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value == null)
            {
                return 0;
            }

            return value switch
            {
                int i => i,
                long l => (int)l,
                double d => (int)d,
                float f => (int)f,
                string s => int.TryParse(s, out var parsed) ? parsed : 0,
                _ => 0,
            };
        }

        private static List<object?> GetList(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value is not List<object?> list)
            {
                return new List<object?>();
            }

            return list;
        }

        [Serializable]
        private sealed class SharedConfig
        {
            public string ServerUrl = string.Empty;
            public string WsUrl = string.Empty;
            public string ApiKey = string.Empty;
            public string WorkerName = string.Empty;
            public string MachineId = string.Empty;

            // Support camelCase fields from config.json
            public string serverUrl = string.Empty;
            public string wsUrl = string.Empty;
            public string apiKey = string.Empty;
            public string workerName = string.Empty;
            public string machineId = string.Empty;

            public string EffectiveServerUrl => !string.IsNullOrWhiteSpace(serverUrl) ? serverUrl : ServerUrl;
            public string EffectiveWsUrl => !string.IsNullOrWhiteSpace(wsUrl) ? wsUrl : WsUrl;
            public string EffectiveApiKey => !string.IsNullOrWhiteSpace(apiKey) ? apiKey : ApiKey;
            public string EffectiveWorkerName => !string.IsNullOrWhiteSpace(workerName) ? workerName : WorkerName;
            public string EffectiveMachineId => !string.IsNullOrWhiteSpace(machineId) ? machineId : MachineId;
        }
    }
}
