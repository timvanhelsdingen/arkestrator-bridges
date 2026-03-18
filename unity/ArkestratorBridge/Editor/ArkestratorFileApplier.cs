using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace ArkestratorBridge
{
    internal static class ArkestratorFileApplier
    {
        internal sealed class ApplyResult
        {
            public int Applied;
            public int Failed;
            public readonly List<string> Errors = new();
        }

        public static ApplyResult ApplyFileChanges(List<object?>? changes, string projectRoot)
        {
            var result = new ApplyResult();
            if (changes == null)
            {
                return result;
            }

            foreach (var entry in changes)
            {
                if (entry is not Dictionary<string, object?> map)
                {
                    result.Failed++;
                    result.Errors.Add("Invalid file change payload entry");
                    continue;
                }

                var relPath = GetString(map, "path");
                if (string.IsNullOrWhiteSpace(relPath))
                {
                    result.Failed++;
                    result.Errors.Add("File change missing path");
                    continue;
                }

                var action = GetString(map, "action").ToLowerInvariant();
                if (string.IsNullOrEmpty(action))
                {
                    action = "modify";
                }

                string absolutePath;
                try
                {
                    absolutePath = ResolvePath(relPath, projectRoot);
                }
                catch (Exception ex)
                {
                    result.Failed++;
                    result.Errors.Add(ex.Message);
                    continue;
                }

                try
                {
                    switch (action)
                    {
                        case "create":
                        case "modify":
                        {
                            var parent = Path.GetDirectoryName(absolutePath);
                            if (!string.IsNullOrEmpty(parent))
                            {
                                Directory.CreateDirectory(parent);
                            }

                            var encoding = GetString(map, "encoding").ToLowerInvariant();
                            var binaryContent = GetString(map, "binaryContent");
                            if (encoding == "base64" && !string.IsNullOrEmpty(binaryContent))
                            {
                                File.WriteAllBytes(absolutePath, Convert.FromBase64String(binaryContent));
                            }
                            else
                            {
                                var content = GetString(map, "content");
                                File.WriteAllText(absolutePath, content, new UTF8Encoding(false));
                            }

                            result.Applied++;
                            break;
                        }
                        case "delete":
                            if (File.Exists(absolutePath))
                            {
                                File.Delete(absolutePath);
                            }
                            result.Applied++;
                            break;
                        default:
                            result.Failed++;
                            result.Errors.Add($"Unknown file action '{action}' for {relPath}");
                            break;
                    }
                }
                catch (Exception ex)
                {
                    result.Failed++;
                    result.Errors.Add($"Failed to apply {relPath}: {ex.Message}");
                }
            }

            return result;
        }

        private static string ResolvePath(string path, string projectRoot)
        {
            var root = Path.GetFullPath(projectRoot);
            var resolved = Path.IsPathRooted(path)
                ? Path.GetFullPath(path)
                : Path.GetFullPath(Path.Combine(root, path));

            var normalizedRoot = root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            var startsWithRoot = resolved.StartsWith(normalizedRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                || resolved.StartsWith(normalizedRoot + Path.AltDirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                || string.Equals(resolved, normalizedRoot, StringComparison.OrdinalIgnoreCase);

            if (!startsWithRoot)
            {
                throw new InvalidOperationException($"Path escapes project root: {path}");
            }

            return resolved;
        }

        private static string GetString(Dictionary<string, object?> map, string key)
        {
            if (!map.TryGetValue(key, out var value) || value == null)
            {
                return string.Empty;
            }

            return value.ToString() ?? string.Empty;
        }
    }
}
