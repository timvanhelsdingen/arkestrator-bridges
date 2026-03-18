using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace ArkestratorBridge
{
    internal sealed class ArkestratorWebSocketClient
    {
        private const double ReconnectBaseSeconds = 3.0;
        private const double ReconnectMaxSeconds = 30.0;

        private readonly ConcurrentQueue<QueuedEvent> _eventQueue = new();
        private readonly object _sendLock = new();

        private ClientWebSocket? _socket;
        private CancellationTokenSource? _cts;
        private Task? _loopTask;
        private bool _shouldReconnect;
        private double _reconnectDelaySeconds = ReconnectBaseSeconds;
        private string _fullUrl = string.Empty;

        public Action? OnConnected;
        public Action? OnDisconnected;
        public Action<string>? OnError;
        public Action<Dictionary<string, object?>>? OnMessage;

        public bool Connected => _socket is { State: WebSocketState.Open };

        public void Connect(string fullUrl)
        {
            _fullUrl = fullUrl;
            _reconnectDelaySeconds = ReconnectBaseSeconds;
            _shouldReconnect = true;

            StopLoop();

            _cts = new CancellationTokenSource();
            _loopTask = Task.Run(() => RunLoopAsync(_cts.Token));
        }

        public void Disconnect()
        {
            _shouldReconnect = false;
            StopLoop();
        }

        public void Poll()
        {
            var max = 100;
            while (max-- > 0 && _eventQueue.TryDequeue(out var evt))
            {
                switch (evt.Type)
                {
                    case EventType.Connected:
                        OnConnected?.Invoke();
                        break;
                    case EventType.Disconnected:
                        OnDisconnected?.Invoke();
                        break;
                    case EventType.Error:
                        OnError?.Invoke(evt.Error ?? "Unknown WebSocket error");
                        break;
                    case EventType.Message:
                        if (evt.Payload != null)
                        {
                            OnMessage?.Invoke(evt.Payload);
                        }
                        break;
                }
            }
        }

        public void SendMessage(Dictionary<string, object?> message)
        {
            if (!Connected || _socket == null)
            {
                return;
            }

            try
            {
                var json = MiniJson.Serialize(message);
                var bytes = Encoding.UTF8.GetBytes(json);
                var segment = new ArraySegment<byte>(bytes);
                lock (_sendLock)
                {
                    if (_socket.State != WebSocketState.Open)
                    {
                        return;
                    }

                    _socket.SendAsync(segment, WebSocketMessageType.Text, true, CancellationToken.None).Wait();
                }
            }
            catch (Exception ex)
            {
                _eventQueue.Enqueue(QueuedEvent.Error($"Send failed: {ex.Message}"));
            }
        }

        private async Task RunLoopAsync(CancellationToken token)
        {
            while (!token.IsCancellationRequested && _shouldReconnect)
            {
                var connected = false;
                try
                {
                    var socket = new ClientWebSocket();
                    _socket = socket;
                    await socket.ConnectAsync(new Uri(_fullUrl), token);
                    connected = true;
                    _reconnectDelaySeconds = ReconnectBaseSeconds;
                    _eventQueue.Enqueue(QueuedEvent.Connected());

                    await ReceiveLoopAsync(socket, token);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    _eventQueue.Enqueue(QueuedEvent.Error(NormalizeConnectionError(ex)));
                }
                finally
                {
                    if (connected)
                    {
                        _eventQueue.Enqueue(QueuedEvent.Disconnected());
                    }

                    if (_socket != null)
                    {
                        try
                        {
                            _socket.Dispose();
                        }
                        catch
                        {
                            // best effort
                        }
                    }

                    _socket = null;
                }

                if (!_shouldReconnect || token.IsCancellationRequested)
                {
                    break;
                }

                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(_reconnectDelaySeconds), token);
                }
                catch (OperationCanceledException)
                {
                    break;
                }

                _reconnectDelaySeconds = Math.Min(_reconnectDelaySeconds * 2.0, ReconnectMaxSeconds);
            }
        }

        private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken token)
        {
            var buffer = new byte[8192];
            var segment = new ArraySegment<byte>(buffer);

            while (socket.State == WebSocketState.Open && !token.IsCancellationRequested)
            {
                var builder = new StringBuilder();
                WebSocketReceiveResult? result = null;

                do
                {
                    result = await socket.ReceiveAsync(segment, token);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        try
                        {
                            await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", token);
                        }
                        catch
                        {
                            // ignore
                        }
                        return;
                    }

                    var chunk = Encoding.UTF8.GetString(buffer, 0, result.Count);
                    builder.Append(chunk);
                }
                while (!result.EndOfMessage);

                var text = builder.ToString();
                var parsed = MiniJson.Deserialize(text) as Dictionary<string, object?>;
                if (parsed == null)
                {
                    continue;
                }

                _eventQueue.Enqueue(QueuedEvent.Message(parsed));
            }
        }

        private static string NormalizeConnectionError(Exception ex)
        {
            var message = ex.Message ?? "Connection failed";
            if (message.Contains("401"))
            {
                return "Authentication failed (401): check API key";
            }

            if (message.Contains("No such host") || message.Contains("Name or service not known"))
            {
                return "Cannot resolve Arkestrator host";
            }

            return message;
        }

        private void StopLoop()
        {
            if (_cts == null)
            {
                return;
            }

            try
            {
                _cts.Cancel();
            }
            catch
            {
                // ignore
            }

            try
            {
                _loopTask?.Wait(TimeSpan.FromSeconds(2));
            }
            catch
            {
                // ignore
            }

            try
            {
                _socket?.Abort();
                _socket?.Dispose();
            }
            catch
            {
                // ignore
            }

            _socket = null;
            _loopTask = null;
            _cts.Dispose();
            _cts = null;
        }

        private enum EventType
        {
            Connected,
            Disconnected,
            Error,
            Message,
        }

        private readonly struct QueuedEvent
        {
            public EventType Type { get; }
            public string? Error { get; }
            public Dictionary<string, object?>? Payload { get; }

            private QueuedEvent(EventType type, string? error, Dictionary<string, object?>? payload)
            {
                Type = type;
                Error = error;
                Payload = payload;
            }

            public static QueuedEvent Connected() => new(EventType.Connected, null, null);
            public static QueuedEvent Disconnected() => new(EventType.Disconnected, null, null);
            public static QueuedEvent Error(string message) => new(EventType.Error, message, null);
            public static QueuedEvent Message(Dictionary<string, object?> payload) => new(EventType.Message, null, payload);
        }
    }
}
