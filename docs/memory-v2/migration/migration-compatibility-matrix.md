# Co-evolving Companion：跨会话长期记忆 V2.1 版本兼容性矩阵 (Migration Compatibility Matrix · Final Freeze Edition)

> **文档元数据**：
> - **阶段定位**：Migration & Compatibility Specification (Compatibility Matrix)
> - **核心目标**：明确不同应用版本与不同数据库文件版本之间的交互行为，防止版本错配引发物理损坏。

---

## 1. 应用与数据库版本全兼容矩阵 (App vs DB Compatibility Matrix)

| 应用程序版本 (Application Release) | 遇到旧版数据库 (DB V1 · user_version == 0) | 遇到过渡期数据库 (Shadow DB in progress) | 遇到新版数据库 (DB V2.1 · user_version == 20261018) |
| :--- | :--- | :--- | :--- |
| **Old App (V1 遗留生产版)** | **正常读写 (原生支持)**<br>- 维护现有 slices/events 表<br>- 维持 dual-write jsonl 模式 | **正常运行 (忽略影子库)**<br>- 影子库为独立文件名，旧版不受任何干扰 | **只读阻断并安全退出 (Fail-Fast)**<br>- 启动检测到 `user_version >= 20261018`<br>- 弹窗：“*数据库已升级到 V2.1，请使用新版程序*”<br>- 严禁强行写入破坏新表！ |
| **Transitional App (过渡兼容版)** | **引导并执行影子迁移**<br>- 启动时执行在线快照备份<br>- 构建影子库并校验<br>- 获得确认后极速原子割接 | **清理残余并重新构建**<br>- 清除未完成的旧影子库<br>- 重新发起确定性迁移 | **正常读写 (全面启用)**<br>- 走 V2.1 规范持久化路径<br>- 兼容视图提供临时只读支持 |
| **New App (V2.1 纯净发布版)** | **自动触发静默升级**<br>- 后台自动完成快照备份与影子迁移<br>- 完成割接并建立新通道 | **自动恢复并完成割接**<br>- 依据迁移日志断点续传或重试 | **原生全功能运行**<br>- 100% 运行于 V2.1 规范体系<br>- 弃用兼容视图 |

---

## 2. 写入者唯一性与单向投影保证 (Writer Cutover Rules)

```text
               [数据库写入者权限控制]
               ├── Legacy V1 时期 : Feeder/Bubble 双写 SQLite slices + JSONL
               ├── 割接窗口期      : 应用程序静默 50ms，禁止一切写操作 (Quiesce Mode)
               └── V2.1 运行期    : 100% 仅由 SQLite 充当单一写入主库 (Single Canonical Master)
                                    JSONL 降级为只读导出副本，严禁直接双写
```

---

## 3. 兼容视图退场里程碑 (Compatibility Views Bounded Deprecation Plan · P1-3)

- **退场治理原则**：不预设僵化的版本号（如不预先绑死在某一特定 Release），而是基于严格的**运行时退场门禁（Bounded Removal Milestones）**：
  1. **代码基线完备**：伴生体生产代码（`src/`）所有读取组件完成向 V2.1 原生表的改造；
  2. **过渡版本退役**：所有过渡版客户端（Transitional App）生命周期结束；
  3. **零读取指标确认**：运行时监控指标确认 `legacy_slices_view` 与 `legacy_events_view` 的查询读取调用连续 7 天严格为 0。
- 只有上述三项条件全部满足时，才正式调度执行 DROP VIEW。
