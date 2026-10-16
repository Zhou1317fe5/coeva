import http from "node:http";

function postEvent(payload) {
  try {
    const data = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: 17321,
        path: "/api/event",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(data),
          "Connection": "close",
        },
        timeout: 500,
      },
      (res) => {
        res.resume();
      }
    );
    req.on("error", () => {});
    req.on("timeout", () => req.destroy());
    req.write(data);
    req.end();
  } catch (_err) {
    // Fail silently so PI-Desktop is never blocked if companion is not running
  }
}

export default function companionBridge(pi) {
  if (!pi || typeof pi.on !== "function") return;

  // 1. Session start
  pi.on("session_start", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "session_start",
      session_id: "pi_session",
    });
  });

  // 2. User prompt -> Thinking
  pi.on("before_agent_start", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "user_prompt",
      session_id: "pi_session",
      message: "🤔 PI-Desktop 思考中...",
    });
  });

  // 3. Tool call -> Working
  pi.on("tool_call", (event) => {
    const toolName = (event && event.toolName) || "tool";
    postEvent({
      agent_id: "pi-desktop",
      event_type: "pre_tool_use",
      session_id: "pi_session",
      tool_name: toolName,
      message: `⚙️ 正在执行: ${toolName}`,
    });
  });

  // 4. Tool result -> Failure alert
  pi.on("tool_result", (event) => {
    if (event && event.isError) {
      const toolName = event.toolName || "tool";
      postEvent({
        agent_id: "pi-desktop",
        event_type: "tool_failure",
        session_id: "pi_session",
        tool_name: toolName,
        message: `⚠️ 工具报错: ${toolName}`,
      });
    }
  });

  // 5. Turn end -> Complete / Celebration
  pi.on("turn_end", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "task_complete",
      session_id: "pi_session",
      message: "🎉 回合完成！",
    });
  });

  // 6. Session shutdown -> Sleep
  pi.on("session_shutdown", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "session_end",
      session_id: "pi_session",
    });
  });
}
