# A 组:LCM 录制与回放 + 离线源

- **状态**:已批准,待实现
- **日期**:2026-06-18
- **范围**:A 组(录制 / 回放 / 离线源)。是「录制回放 → 导出 → 实时监控 → 类型诊断」四步走的第一步。

## 1. 目标

新增 3 项能力,构成「现场复现 → 工位反复分析」闭环:

1. `lcm record` —— 录制实时组播流量到标准 LCM `.log` 文件(二进制兼容 `lcm-logger`)。
2. `lcm play` —— 按原始时间间隔回放 `.log` 到组播网络。
3. 现有命令 `echo` / `stats` / `list` 新增 `--from <file.log>` —— 直接读离线日志,反复分析不必反复录制。

**核心准则**:所有 LCM 日志读写纯 Python,零外部依赖;输出文件可被 `lcm-logger` / `lcm-logplayer` / `lcm.EventLog` 直接读取。

## 2. 核心模块:统一数据源抽象层

引入抽象,让「实时组播」和「离线日志」走同一条处理管线。这是本设计的结构性收益——后续 B/C 组可直接复用。

```
src/lcm_tools/source.py          # 新文件:统一数据源抽象
├── PacketSource (Protocol)
│   └── start(callback: PacketCallback, stop_event: threading.Event) -> None
├── LiveSource          # 包裹现有 run_listener(实时组播)
└── LogFileSource       # 读 .log 文件,按 event 时间戳间隔投递 callback
```

**每个命令的改造模式统一且极小**:

```python
# 改造前
stop_event = run_listener(callback, mc_addr=..., mc_port=...)

# 改造后
source = make_source(args)   # args.from 有值 → LogFileSource,否则 LiveSource
stop_event = source.start(callback)
```

### LogFileSource 关键行为

- 顺序读取每个 event(LCM 日志本就有序)。
- 用 `time.monotonic()` 计算相邻 event 的时间差并 `sleep`,忠实还原原始节奏。
- 内置 `speed: float = 1.0` 倍速参数(C 组回放控制可复用)。
- `duration: Optional[float]`:限制投递时长。

## 3. LCM 日志读写模块

```
src/lcm_tools/lcm_log.py         # 新文件:标准 LCM 日志格式 I/O
├── write_lcm_log(path, events)                # 写(录制用)
├── iter_lcm_log(path) -> Iterator[LogEvent]   # 读(回放/离线源用)
└── LogEvent(eventnum:int, timestamp_us:int, channel:str, data:bytes)
```

### 二进制格式(严格遵循官方规范,大端序)

- 文件无全局头,直接是 event 序列。
- 每个 event = sync word + event 头 + channel 字节串(无 null 结尾)+ data。
- sync word:`0xEDA1DA01`(每个 event 头部最前面的 4 字节 magic)。

```
[magic: uint32 = 0xEDA1DA01]   # sync word
[eventnum: uint32]             # 从 0 递增
[time_sec:  uint32]            # Unix 秒
[time_usec: uint32]            # 微秒部分(< 1_000_000)
[chan_len:  uint32]            # channel 字节数(不含 null)
[data_len:  uint32]            # payload 字节数
[channel:   chan_len bytes]    # 注意:日志里无 null 结尾
[data:      data_len bytes]
```

timestamp 用 wall clock `time.time()` 的微秒(`lcm-logger` 约定 utime = microseconds since epoch)。

> ⚠️ 写入侧需保证 channel 字节串不含 null 结尾(与组播协议相反);读取侧据此长度读取。

## 4. 新增命令

### `lcm record`

```
lcm record [-o out.log] [--channel "CAM.*"] [--duration 60]
           [--lcm-url ADDR] [--lcm-port PORT]
```

- 默认输出文件名:`lcm_<YYYYMMDD_HHMMSS>.log`。
- **不传 `--channel` 时录制所有话题**(监听整个组播组)。
- `--channel`:正则过滤(复用 echo 的 `re.compile` 套路)。
- `--duration`:录 N 秒后自动停;不指定则 Ctrl+C 停。
- 实时进度:`Recording → out.log | 1234 events | 1.2 MB | 0:00:23`(rich 状态行)。
- **录制内容决策(方案 A)**:只记录有 channel 字段的包(`pkt.has_channel` 为真),即 short message 和 fragment 的第 0 包;跳过 `channel=None` 的后续分片包。
  - 理由:第 0 包已携带 channel + 头部 payload,足以标识消息;后续纯数据 fragment 无 channel 信息,离线分析用不上,记下来反而是噪音。
  - 取舍:>64KB 超大消息回放不完整。LCM 实践中极少,可接受;完整重组归 D 组范畴。
  - 实现统一性:「录全部」与「录过滤」走同一条路径——先判 `has_channel`,再做正则匹配。
- timestamp:wall clock 微秒。

### `lcm play`

```
lcm play <file.log> [--speed 1.0] [--loop] [--channel "CAM.*"]
         [--lcm-url ADDR] [--lcm-port PORT]
```

- 读日志 → 用相邻 event 时间差 `sleep` → 通过 UDP 组播 socket 发送。
- `--speed`:>1 加速,<1 慢放(默认 1.0 忠实回放)。
- `--loop`:循环回放。
- `--channel`:正则过滤(发送前过滤)。
- 发送侧:新建轻量 sender(普通 UDP socket,`sendto` 到组播地址),复用 `listener.py` 的组播地址常量。
- 进度显示:`Playing demo.log | 1234/5678 events | 0:42/2:15 | speed 1.0x`。

### 现有命令加 `--from`

```bash
lcm topic echo EXAMPLE --from demo.log          # 离线分析
lcm topic stats --from demo.log --duration 30   # 统计离线窗口
lcm topic list --from demo.log                  # 列出日志里的 channel
```

- `--from` 与 `--lcm-url/--lcm-port` 互斥(传了 `--from` 就不监听组播)。
- `LogFileSource` 忠实按节奏投递;`--duration` 限制回放时长。
- echo 的 `count`/`timeout` 在离线模式下语义不变。

## 5. CLI 结构

```
lcm/
├── topic (echo / list / stats)   ← 三者加 --from
├── node (list)
├── record                         ← 新顶层命令(对齐 ros2 bag record)
└── play                           ← 新顶层命令(对齐 ros2 bag play)
```

`record` / `play` 放顶层,语义比塞进 `topic` 子组自然。

## 6. 错误处理

- 日志读取遇坏 sync word → 抛清晰错误并指出字节偏移量。
- `--from` 文件不存在 / 非 `.log` → 友好报错退出。
- `play` 发送失败(组播路由未配)→ 提示检查路由(复用 README 已有提示)。
- Ctrl+C:
  - `record` 确保已缓冲数据 flush 落盘后退出。
  - `play` 立即停止发送。

## 7. 测试策略

- **lcm_log 读写 round-trip**:write 一批 event → read 回来字段全等。
- **格式兼容性**:用 `lcm_ref/test/python/example.lcmlog` 作为 fixture,确保 `iter_lcm_log` 能正确解析官方样本。
- **LogFileSource**:mock 日志,验证 sleep 间隔与 timestamp 差一致(monkeypatch 控制 sleep)。
- **record/play 集成**:record 录一段 → play 回放 → echo/stats `--from` 验证数据流通(monkeypatch mock socket,避免依赖真实组播环境)。
- 现有 stats/echo/list 测试加 `--from` 用例。

## 8. 架构收益

引入 `PacketSource` 抽象层后,未来 B 组(导出)、C 组(实时监控增强)直接复用——任何命令都「不关心数据从哪来」,对整个工具链是结构性提升。

## 9. 不做的事(YAGNI 边界)

- ❌ 分片重组(方案 A:保真记录原始流,只录有 channel 的包)。
- ❌ 录制日志分割 / 轮转(`--max-size --rotate`)。
- ❌ `play` 的 `--start/--end` 时间范围裁剪。
- ❌ 索引文件(LCM 日志顺序读已足够快)。
- ❌ 录制压缩(留给系统层 `gzip`)。

## 10. 落地顺序(实现计划骨架)

1. `lcm_log.py`(读写 + round-trip 测试 + 官方样本兼容测试)——最底层,零依赖,先稳。
2. `source.py`(`PacketSource` / `LiveSource` / `LogFileSource` + make_source + 测试)。
3. `record` 命令(用 lcm_log 写 + LiveSource 录 + 进度显示)。
4. `play` 命令(用 lcm_log 读 + 组播 sender + 进度显示)。
5. `echo`/`stats`/`list` 接入 `--from`(走 LogFileSource,改动最小)。
6. 文档更新(README / README_zh 新增 record/play/--from 章节)。
