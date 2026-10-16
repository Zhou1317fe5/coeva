import http from "node:http";
import { randomUUID } from "node:crypto";

const COMPANION_PORT = 17321;

// One id per PI-Desktop session, so the companion can group telemetry into
// episodes. A hardcoded id collapsed every session the user ever ran into a
// single episode, which made any cross-session pattern impossible.
let sessionId = newSessionId();

function newSessionId() {
  return `pi-${randomUUID()}`;
}

function postEvent(payload) {
  try {
    const data = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: COMPANION_PORT,
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

  // 1. Session start -> new episode boundary
  pi.on("session_start", () => {
    sessionId = newSessionId();
    postEvent({
      agent_id: "pi-desktop",
      event_type: "session_start",
      session_id: sessionId,
    });
  });

  // 2. User prompt -> Thinking
  pi.on("before_agent_start", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "user_prompt",
      session_id: sessionId,
      message: "🤔 PI-Desktop 思考中...",
    });
  });

  // 3. Tool call -> Working
  pi.on("tool_call", (event) => {
    const toolName = (event && event.toolName) || "tool";
    postEvent({
      agent_id: "pi-desktop",
      event_type: "pre_tool_use",
      session_id: sessionId,
      tool_name: toolName,
      message: `⚙️ 正在执行: ${toolName}`,
    });
  });

  // 4. Tool result -> completion or failure. A successful result used to emit
  //    nothing at all, so the companion only ever learned about failures.
  pi.on("tool_result", (event) => {
    const toolName = (event && event.toolName) || "tool";
    if (event && event.isError) {
      postEvent({
        agent_id: "pi-desktop",
        event_type: "tool_failure",
        session_id: sessionId,
        tool_name: toolName,
        message: `⚠️ 工具报错: ${toolName}`,
      });
    } else {
      postEvent({
        agent_id: "pi-desktop",
        event_type: "post_tool_use",
        session_id: sessionId,
        tool_name: toolName,
      });
    }
  });

  // 5. Turn end -> the agent finished one exchange, which is not the same as the
  //    user's task being complete. Reporting it as `task_complete` produced ~450
  //    "completed task" events per working day.
  pi.on("turn_end", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "turn_end",
      session_id: sessionId,
    });
  });

  // 6. Session shutdown -> Sleep
  pi.on("session_shutdown", () => {
    postEvent({
      agent_id: "pi-desktop",
      event_type: "session_end",
      session_id: sessionId,
    });
  });
}
