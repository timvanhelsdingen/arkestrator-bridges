using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace ArkestratorBridge
{
    internal static class ArkestratorCommandExecutor
    {
        internal sealed class ExecutionResult
        {
            public int Executed;
            public int Failed;
            public int Skipped;
            public readonly List<string> Errors = new();
            public string Stdout = "";
            public string Stderr = "";
        }

        public static ExecutionResult ExecuteCommands(List<object?>? commands)
        {
            var result = new ExecutionResult();
            if (commands == null)
            {
                return result;
            }

            var stdoutLines = new List<string>();
            var stderrLines = new List<string>();
            void LogHandler(string message, string stackTrace, LogType type)
            {
                if (type == LogType.Error || type == LogType.Exception)
                    stderrLines.Add(message);
                else
                    stdoutLines.Add(message);
            }
            Application.logMessageReceived += LogHandler;
            try
            {

            foreach (var entry in commands)
            {
                if (entry is not Dictionary<string, object?> command)
                {
                    result.Skipped++;
                    result.Errors.Add("Invalid command payload entry");
                    continue;
                }

                var language = GetString(command, "language").ToLowerInvariant();
                var script = GetString(command, "script");
                var description = GetString(command, "description");

                if (string.IsNullOrWhiteSpace(script))
                {
                    result.Skipped++;
                    continue;
                }

                if (language is "unity_json" or "json")
                {
                    ExecuteUnityJson(script, description, result);
                    continue;
                }

                result.Skipped++;
                result.Errors.Add($"Unsupported language '{language}' (supported: unity_json/json)");
            }

            }
            finally
            {
                Application.logMessageReceived -= LogHandler;
            }
            if (stdoutLines.Count > 0)
                result.Stdout = string.Join("\n", stdoutLines);
            if (stderrLines.Count > 0)
                result.Stderr = string.Join("\n", stderrLines);

            return result;
        }

        private static void ExecuteUnityJson(string script, string description, ExecutionResult result)
        {
            object? parsed;
            try
            {
                parsed = MiniJson.Deserialize(script);
            }
            catch (Exception ex)
            {
                result.Failed++;
                result.Errors.Add($"JSON parse failed ({description}): {ex.Message}");
                return;
            }

            if (parsed is List<object?> list)
            {
                foreach (var item in list)
                {
                    ExecuteInstruction(item, description, result);
                }
                return;
            }

            ExecuteInstruction(parsed, description, result);
        }

        private static void ExecuteInstruction(object? payload, string description, ExecutionResult result)
        {
            if (payload is not Dictionary<string, object?> command)
            {
                result.Failed++;
                result.Errors.Add($"Instruction is not an object ({description})");
                return;
            }

            var action = GetString(command, "action").ToLowerInvariant();
            if (string.IsNullOrEmpty(action))
            {
                result.Failed++;
                result.Errors.Add($"Instruction missing action ({description})");
                return;
            }

            try
            {
                switch (action)
                {
                    case "ping":
                        result.Executed++;
                        break;
                    case "create_game_object":
                        CreateGameObject(command);
                        result.Executed++;
                        break;
                    case "delete_game_object":
                        DeleteGameObject(command);
                        result.Executed++;
                        break;
                    case "set_position":
                        SetGameObjectPosition(command);
                        result.Executed++;
                        break;
                    case "open_scene":
                        OpenScene(command);
                        result.Executed++;
                        break;
                    case "save_scenes":
                        EditorSceneManager.SaveOpenScenes();
                        result.Executed++;
                        break;
                    case "select_asset":
                        SelectAsset(command);
                        result.Executed++;
                        break;
                    case "refresh_assets":
                        AssetDatabase.Refresh();
                        result.Executed++;
                        break;
                    default:
                        result.Failed++;
                        result.Errors.Add($"Unknown unity_json action '{action}' ({description})");
                        break;
                }
            }
            catch (Exception ex)
            {
                result.Failed++;
                result.Errors.Add($"Action '{action}' failed ({description}): {ex.Message}");
            }
        }

        private static void CreateGameObject(Dictionary<string, object?> command)
        {
            var name = GetString(command, "name");
            if (string.IsNullOrWhiteSpace(name))
            {
                name = "AgentObject";
            }

            var gameObject = new GameObject(name);
            Undo.RegisterCreatedObjectUndo(gameObject, "Arkestrator Create GameObject");

            var parentPath = GetString(command, "parentPath");
            if (!string.IsNullOrWhiteSpace(parentPath))
            {
                var parent = FindGameObjectByPath(parentPath);
                if (parent != null)
                {
                    gameObject.transform.SetParent(parent.transform, false);
                }
            }

            var position = ReadVector3(command, "position");
            if (position.HasValue)
            {
                gameObject.transform.position = position.Value;
            }

            Selection.activeGameObject = gameObject;
        }

        private static void DeleteGameObject(Dictionary<string, object?> command)
        {
            var path = GetString(command, "path");
            var name = GetString(command, "name");

            GameObject? target = null;
            if (!string.IsNullOrWhiteSpace(path))
            {
                target = FindGameObjectByPath(path);
            }
            if (target == null && !string.IsNullOrWhiteSpace(name))
            {
                target = GameObject.Find(name);
            }
            if (target == null)
            {
                throw new InvalidOperationException("Target GameObject not found");
            }

            Undo.DestroyObjectImmediate(target);
        }

        private static void SetGameObjectPosition(Dictionary<string, object?> command)
        {
            var path = GetString(command, "path");
            var name = GetString(command, "name");
            var position = ReadVector3(command, "position");
            if (!position.HasValue)
            {
                throw new InvalidOperationException("set_position requires a position array [x,y,z]");
            }

            GameObject? target = null;
            if (!string.IsNullOrWhiteSpace(path))
            {
                target = FindGameObjectByPath(path);
            }
            if (target == null && !string.IsNullOrWhiteSpace(name))
            {
                target = GameObject.Find(name);
            }
            if (target == null)
            {
                throw new InvalidOperationException("Target GameObject not found");
            }

            Undo.RecordObject(target.transform, "Arkestrator Set Position");
            target.transform.position = position.Value;
        }

        private static void OpenScene(Dictionary<string, object?> command)
        {
            var path = GetString(command, "path");
            if (string.IsNullOrWhiteSpace(path))
            {
                throw new InvalidOperationException("open_scene requires 'path'");
            }

            EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
        }

        private static void SelectAsset(Dictionary<string, object?> command)
        {
            var path = GetString(command, "path");
            if (string.IsNullOrWhiteSpace(path))
            {
                throw new InvalidOperationException("select_asset requires 'path'");
            }

            var asset = AssetDatabase.LoadMainAssetAtPath(path);
            if (asset == null)
            {
                throw new InvalidOperationException($"Asset not found: {path}");
            }

            Selection.activeObject = asset;
            EditorGUIUtility.PingObject(asset);
        }

        private static Vector3? ReadVector3(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value is not List<object?> numbers || numbers.Count < 3)
            {
                return null;
            }

            return new Vector3(
                ToFloat(numbers[0]),
                ToFloat(numbers[1]),
                ToFloat(numbers[2])
            );
        }

        private static float ToFloat(object? value)
        {
            if (value == null)
            {
                return 0f;
            }

            return value switch
            {
                float f => f,
                double d => (float)d,
                long l => l,
                int i => i,
                _ => float.TryParse(value.ToString(), out var parsed) ? parsed : 0f,
            };
        }

        private static string GetString(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value == null)
            {
                return string.Empty;
            }

            return value.ToString() ?? string.Empty;
        }

        private static GameObject? FindGameObjectByPath(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                return null;
            }

            var segments = path.Split('/');
            if (segments.Length == 0)
            {
                return null;
            }

            var root = GameObject.Find(segments[0]);
            if (root == null)
            {
                return null;
            }

            var current = root.transform;
            for (var i = 1; i < segments.Length; i++)
            {
                var child = current.Find(segments[i]);
                if (child == null)
                {
                    return null;
                }
                current = child;
            }

            return current.gameObject;
        }
    }
}
