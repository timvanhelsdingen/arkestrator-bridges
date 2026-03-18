using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace ArkestratorBridge
{
    // Lightweight JSON parser/serializer for Unity editor tooling.
    // Adapted from Unity's MiniJSON reference implementation.
    internal static class MiniJson
    {
        public static object? Deserialize(string json)
        {
            if (json == null)
            {
                return null;
            }

            return Parser.Parse(json);
        }

        public static string Serialize(object? obj)
        {
            return Serializer.Serialize(obj);
        }

        private sealed class Parser : IDisposable
        {
            private const string WordBreak = "{}[],:\"";

            private readonly StringReader _json;

            private Parser(string json)
            {
                _json = new StringReader(json);
            }

            public static object? Parse(string json)
            {
                using var instance = new Parser(json);
                return instance.ParseValue();
            }

            public void Dispose()
            {
                _json.Dispose();
            }

            private enum Token
            {
                None,
                CurlyOpen,
                CurlyClose,
                SquaredOpen,
                SquaredClose,
                Colon,
                Comma,
                String,
                Number,
                True,
                False,
                Null,
            }

            private Dictionary<string, object?> ParseObject()
            {
                var table = new Dictionary<string, object?>();

                _json.Read();

                while (true)
                {
                    switch (NextToken)
                    {
                        case Token.None:
                            return table;
                        case Token.Comma:
                            continue;
                        case Token.CurlyClose:
                            return table;
                        default:
                        {
                            var name = ParseString();
                            if (name == null)
                            {
                                return table;
                            }

                            if (NextToken != Token.Colon)
                            {
                                return table;
                            }

                            _json.Read();
                            table[name] = ParseValue();
                            break;
                        }
                    }
                }
            }

            private List<object?> ParseArray()
            {
                var array = new List<object?>();

                _json.Read();

                var parsing = true;
                while (parsing)
                {
                    var token = NextToken;
                    switch (token)
                    {
                        case Token.None:
                            return array;
                        case Token.Comma:
                            continue;
                        case Token.SquaredClose:
                            parsing = false;
                            break;
                        default:
                            array.Add(ParseByToken(token));
                            break;
                    }
                }

                return array;
            }

            private object? ParseValue()
            {
                return ParseByToken(NextToken);
            }

            private object? ParseByToken(Token token)
            {
                return token switch
                {
                    Token.String => ParseString(),
                    Token.Number => ParseNumber(),
                    Token.CurlyOpen => ParseObject(),
                    Token.SquaredOpen => ParseArray(),
                    Token.True => true,
                    Token.False => false,
                    Token.Null => null,
                    _ => null,
                };
            }

            private string? ParseString()
            {
                var sb = new StringBuilder();
                _json.Read();

                var parsing = true;
                while (parsing)
                {
                    if (_json.Peek() == -1)
                    {
                        break;
                    }

                    var c = NextChar;
                    switch (c)
                    {
                        case '"':
                            parsing = false;
                            break;
                        case '\\':
                            if (_json.Peek() == -1)
                            {
                                parsing = false;
                                break;
                            }
                            var escaped = NextChar;
                            switch (escaped)
                            {
                                case '"':
                                case '\\':
                                case '/':
                                    sb.Append(escaped);
                                    break;
                                case 'b':
                                    sb.Append('\b');
                                    break;
                                case 'f':
                                    sb.Append('\f');
                                    break;
                                case 'n':
                                    sb.Append('\n');
                                    break;
                                case 'r':
                                    sb.Append('\r');
                                    break;
                                case 't':
                                    sb.Append('\t');
                                    break;
                                case 'u':
                                {
                                    var hex = new char[4];
                                    for (var i = 0; i < 4; i++)
                                    {
                                        hex[i] = NextChar;
                                    }
                                    sb.Append((char)Convert.ToInt32(new string(hex), 16));
                                    break;
                                }
                            }
                            break;
                        default:
                            sb.Append(c);
                            break;
                    }
                }

                return sb.ToString();
            }

            private object ParseNumber()
            {
                var number = NextWord;
                if (number.IndexOf('.') == -1)
                {
                    if (long.TryParse(number, out var parsedLong))
                    {
                        return parsedLong;
                    }
                }

                if (double.TryParse(number, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out var parsedDouble))
                {
                    return parsedDouble;
                }

                return 0d;
            }

            private void EatWhitespace()
            {
                while (char.IsWhiteSpace(PeekChar))
                {
                    _json.Read();
                    if (_json.Peek() == -1)
                    {
                        break;
                    }
                }
            }

            private char PeekChar
            {
                get
                {
                    var peek = _json.Peek();
                    return peek == -1 ? '\0' : Convert.ToChar(peek);
                }
            }

            private char NextChar => Convert.ToChar(_json.Read());

            private string NextWord
            {
                get
                {
                    var sb = new StringBuilder();
                    while (!IsWordBreak(PeekChar))
                    {
                        sb.Append(NextChar);
                        if (_json.Peek() == -1)
                        {
                            break;
                        }
                    }
                    return sb.ToString();
                }
            }

            private Token NextToken
            {
                get
                {
                    EatWhitespace();

                    if (_json.Peek() == -1)
                    {
                        return Token.None;
                    }

                    return PeekChar switch
                    {
                        '{' => Token.CurlyOpen,
                        '}' =>
                            _json.Read() >= 0 ? Token.CurlyClose : Token.None,
                        '[' => Token.SquaredOpen,
                        ']' =>
                            _json.Read() >= 0 ? Token.SquaredClose : Token.None,
                        ',' =>
                            _json.Read() >= 0 ? Token.Comma : Token.None,
                        '"' => Token.String,
                        ':' => Token.Colon,
                        >= '0' and <= '9' or '-' => Token.Number,
                        _ => NextWord switch
                        {
                            "false" => Token.False,
                            "true" => Token.True,
                            "null" => Token.Null,
                            _ => Token.None,
                        },
                    };
                }
            }

            private static bool IsWordBreak(char c)
            {
                return char.IsWhiteSpace(c) || WordBreak.IndexOf(c) != -1;
            }
        }

        private sealed class Serializer
        {
            private readonly StringBuilder _builder;

            private Serializer()
            {
                _builder = new StringBuilder();
            }

            public static string Serialize(object? obj)
            {
                var instance = new Serializer();
                instance.SerializeValue(obj);
                return instance._builder.ToString();
            }

            private void SerializeValue(object? value)
            {
                switch (value)
                {
                    case null:
                        _builder.Append("null");
                        break;
                    case string str:
                        SerializeString(str);
                        break;
                    case bool boolean:
                        _builder.Append(boolean ? "true" : "false");
                        break;
                    case IList list:
                        SerializeArray(list);
                        break;
                    case IDictionary dictionary:
                        SerializeObject(dictionary);
                        break;
                    case char ch:
                        SerializeString(ch.ToString());
                        break;
                    default:
                        if (IsNumeric(value))
                        {
                            SerializeNumber(Convert.ToDouble(value));
                        }
                        else
                        {
                            SerializeString(value.ToString() ?? string.Empty);
                        }
                        break;
                }
            }

            private void SerializeObject(IDictionary obj)
            {
                var first = true;
                _builder.Append('{');
                foreach (DictionaryEntry entry in obj)
                {
                    if (!first)
                    {
                        _builder.Append(',');
                    }

                    SerializeString(entry.Key.ToString() ?? string.Empty);
                    _builder.Append(':');
                    SerializeValue(entry.Value);
                    first = false;
                }
                _builder.Append('}');
            }

            private void SerializeArray(IList array)
            {
                _builder.Append('[');
                var first = true;
                foreach (var item in array)
                {
                    if (!first)
                    {
                        _builder.Append(',');
                    }
                    SerializeValue(item);
                    first = false;
                }
                _builder.Append(']');
            }

            private void SerializeString(string str)
            {
                _builder.Append('"');
                foreach (var c in str)
                {
                    switch (c)
                    {
                        case '"':
                            _builder.Append("\\\"");
                            break;
                        case '\\':
                            _builder.Append("\\\\");
                            break;
                        case '\b':
                            _builder.Append("\\b");
                            break;
                        case '\f':
                            _builder.Append("\\f");
                            break;
                        case '\n':
                            _builder.Append("\\n");
                            break;
                        case '\r':
                            _builder.Append("\\r");
                            break;
                        case '\t':
                            _builder.Append("\\t");
                            break;
                        default:
                            var codepoint = Convert.ToInt32(c);
                            if (codepoint is >= 32 and <= 126)
                            {
                                _builder.Append(c);
                            }
                            else
                            {
                                _builder.Append("\\u");
                                _builder.Append(codepoint.ToString("x4"));
                            }
                            break;
                    }
                }
                _builder.Append('"');
            }

            private void SerializeNumber(double number)
            {
                _builder.Append(number.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
            }

            private static bool IsNumeric(object value)
            {
                return value is sbyte
                    or byte
                    or short
                    or ushort
                    or int
                    or uint
                    or long
                    or ulong
                    or float
                    or double
                    or decimal;
            }
        }
    }
}
