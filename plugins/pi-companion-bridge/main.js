/**
 * 桌面伴生体心跳桥接 — PI-Desktop plugin entry.
 */

async function onLoad() {
  await pi.commands.register({
    id: "companion.openPanel",
    title: "桌面伴生体: 打开控制台",
    keywords: ["companion", "pet", "桌宠", "伴生体"],
    run: async () => {
      await pi.ui.openPanel({ title: "桌面伴生体控制台" });
    },
  });
}

async function onUnload() {
  await pi.commands.unregister("companion.openPanel");
}

module.exports = { onLoad, onUnload };
