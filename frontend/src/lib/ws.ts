export class WSClient {
  private ws: WebSocket;
  constructor(url = "ws://localhost:8000/ws") {
    this.ws = new WebSocket(url);
  }
  send(obj: unknown) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(obj));
    }
  }
}
