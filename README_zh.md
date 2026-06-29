# LCM CLI Tools

[English](README.md) | **中文**

> LCM 命令行工具集 — 用于监控和调试 LCM（Lightweight Communications and Marshalling）网络。

## 功能概览

```
lcm topic echo <channel>   — 实时查看话题数据
lcm topic list             — 列出活跃话题/通道
lcm topic stats            — 实时监控话题统计：频率、带宽、消息数、数据量
lcm topic bw <channel>     — 监控单通道带宽，支持 sparkline 趋势图
lcm topic info <channel>   — 显示通道详细信息和类型结构
lcm node list              — 列出发现的发布节点
lcm type list              — 列出所有已注册的 LCM 类型
lcm type show <type>       — 显示类型字段结构
lcm record                 — 录制 LCM 流量到 .log 文件
lcm play <file.log>        — 回放 .log 文件到组播网络
lcm dashboard              — 启动 Web 可视化仪表盘
```

**亮点**:
- 内置纯 Python `.lcm` 文件解析器，无需安装 `lcm-gen` 或配置 `PYTHONPATH`
- **Web 仪表盘**: 类 Foxglove 的实时可视化界面，支持任意浏览器访问（`lcm dashboard`）
- **消息导出**: 支持 CSV/JSONL 导出，可提取指定字段（`--csv`, `--jsonl`, `--field`）
- **高级监控**: 统计排序/筛选（`--sort`, `--top`, `--freeze`, `--spark`）
- **实时刷新**: topic/node list 支持持续刷新模式（`--watch`）
- **录制回放**: 完整日志文件支持，与 `lcm-logger` 兼容

## 安装

```bash
# 从 PyPI 安装
pip install lcm-cli

# 从源码安装（开发模式）
git clone https://github.com/Joyserr/lcm-cli.git
cd lcm-cli
pip install -e .

# 如需传统 lcm-gen Python 包解码支持（可选）
pip install lcm-cli[decode]

# 如需 Web 仪表盘功能（可选）
pip install lcm-cli[dashboard]
```

**依赖**: Python >= 3.9, `typer`, `rich`。可选依赖：`lcm`（传统解码）、`fastapi` + `uvicorn`（仪表盘）。

## 快速开始

```bash
# 查看所有子命令
lcm --help

# 显示版本
lcm --version

# 列出活跃通道（监听 5 秒）
lcm topic list

# 持续刷新模式（实时更新）
lcm topic list --watch

# 实时查看特定通道的消息（原始 hex 格式）
lcm topic echo EXAMPLE

# 只接收 10 条消息
lcm topic echo EXAMPLE -n 10

# 用正则匹配多个通道
lcm topic echo "CAM.*"

# 监控所有通道的实时统计
lcm topic stats

# 按带宽排序，显示前 5 个
lcm topic stats --sort bw --top 5

# 冻结模式（单次快照）
lcm topic stats --freeze

# 监控带宽，显示趋势图
lcm topic bw CAMERA --spark

# 查看通道详细信息
lcm topic info CAMERA --lcm-file types/

# 列出发现的发布节点
lcm node list
```

## Web 仪表盘

`lcm dashboard` 命令启动一个基于 Web 的实时可视化界面 —— 类似 Foxglove 但专为 LCM 数据设计。支持局域网内任意浏览器访问。

```bash
# 安装仪表盘依赖
pip install lcm-cli[dashboard]

# 启动仪表盘（默认地址: http://0.0.0.0:8080）
lcm dashboard --lcm-file types/

# 自定义端口和绑定地址
lcm dashboard --lcm-file types/ --port 9000 --bind 0.0.0.0

# 从日志文件回放（而非实时组播）
lcm dashboard --from recording.log --lcm-file types/
```

**功能特性**:
- **实时曲线绘制**: 点击任意数值字段即可绘制实时曲线（基于 uPlot）
- **帧率显示**: 每个话题实时显示当前帧率（Hz）
- **跨话题对比**: Compare 模式可将不同通道的字段叠加在同一面板中对比
- **多面板布局**: 可添加/删除/重命名图表面板，每个面板支持多条曲线
- **逐序列统计**: 每条曲线显示 Last/Min/Max/Agg 统计值
- **暂停/恢复**: 全局暂停数据流以检查特定时刻
- **远程访问**: 绑定 `0.0.0.0` 即可从网络中任意设备查看
- **Apple 风格 UI**: 简洁现代的界面设计，毛玻璃效果

**技术栈**: FastAPI（后端）+ React/TypeScript + uPlot（前端）+ WebSocket（实时数据推送）

**测试数据发布器**（用于开发/测试）:
```bash
python3 scripts/publish_test.py --loop --count 50 --interval 2.0 --lcm-file test_lcm_types/
```

## 录制与回放

```bash
# 录制所有通道到 .log 文件
lcm record

# 录制特定通道（支持正则）
lcm record --channel "CAM.*" -o camera.log

# 录制固定时长
lcm record -d 60  # 60 秒

# 回放 .log 文件
lcm play camera.log

# 以 2 倍速回放
lcm play camera.log --speed 2.0

# 循环回放
lcm play camera.log --loop
```

## 消息导出

```bash
# 导出为 CSV（表头自动从首条消息确定）
lcm topic echo EXAMPLE --csv output.csv

# 导出为 JSON Lines
lcm topic echo EXAMPLE --jsonl output.jsonl

# 提取指定字段
lcm topic echo EXAMPLE --field position --field velocity --csv data.csv

# 提取嵌套字段
lcm topic echo EXAMPLE --field imu.accel.x --field imu.gyro.y

# 提取数组切片
lcm topic echo EXAMPLE --field "position[0:2]"

# 自定义时间戳格式
lcm topic echo EXAMPLE --csv data.csv --ts-format iso
```

## 高级统计

```bash
# 按消息频率排序
lcm topic stats --sort rate

# 显示带宽前 10 的通道
lcm topic stats --sort bw --top 10

# 单次快照（非交互模式）
lcm topic stats --freeze

# 添加 sparkline 趋势可视化
lcm topic stats --spark

# 监控单通道带宽
lcm topic bw CAMERA --window 10 --spark

# 从日志文件读取统计
lcm topic stats --from recording.log
```

## 消息解码

### 类型诊断

```bash
# 列出所有已注册的类型
lcm type list

# 按包名筛选
lcm type list --package exlcm

# 显示类型结构
lcm type show example_t --lcm-file types/

# 搜索类型
lcm type list --grep "sensor"
```

### 方式一：直接指定 `.lcm` 文件（推荐）

无需安装 `lcm-gen`，无需配置 `PYTHONPATH`，工具内置纯 Python 解析器：

```bash
# 指定单个 .lcm 文件，自动按 fingerprint 匹配消息类型
lcm topic echo EXAMPLE --lcm-file types/example_t.lcm

# 指定目录（递归扫描所有 .lcm 文件）
lcm topic echo EXAMPLE -f types/

# 指定多个路径
lcm topic echo EXAMPLE -f types/ -f extra_types/

# 指定具体类型名（当 .lcm 文件中有多个 struct 时）
lcm topic echo EXAMPLE -f types/ --type example_t
```

支持完整的 LCM 类型系统：
- 所有原始类型（`int8_t` ~ `int64_t`、`float`、`double`、`string`、`boolean`、`byte`）
- 固定长度数组和变长数组（`double position[3]`、`int16_t ranges[num_ranges]`）
- 多维数组（`int32_t data[size_a][size_b][size_c]`）
- 嵌套结构体和跨文件类型引用
- 递归类型（如链表 `node_t` 中的 `node_t children[n]`）
- 常量声明（`const int32_t MAX_SIZE = 100`）

**工作原理**：解析 `.lcm` 文件 → 内存中构建解码类（`type()` 动态创建） → 按 payload 前 8 字节 fingerprint 自动匹配 → 解码并递归展开嵌套结构体。全程不生成任何文件。

### 方式二：传统 `lcm-gen` 生成文件

```bash
# 安装 lcm Python 包
pip install lcm-cli[decode]

# 先用 lcm-gen 生成 Python 文件，并配置 PYTHONPATH
lcm-gen --python -d types/ types/example_t.lcm
export PYTHONPATH=types:$PYTHONPATH

# 使用 --type 指定解码类（module.Class 格式）
lcm topic echo EXAMPLE --type exlcm.example_t
```

### 自定义组播地址

```bash
lcm topic list --lcm-url 239.255.76.68 --lcm-port 7668
```

### 统计说明

| 指标 | 说明 |
|------|------|
| Rate (Hz) | 滑动窗口内的消息频率（最近 2000 条消息）|
| BW (KB/s) | 滑动窗口内的带宽 |
| Avg Size (B) | 每个消息的平均字节数 |
| Total (KB) | 累计传输总量 |

## 架构

```
┌───────────────────────────────────────────────┐
│                  CLI 层 (Typer)               │
│   topic echo │ topic list │ topic stats│ node │
├───────────────────────────────────────────────┤
│            显示层 (Rich Panel)                │
│   递归嵌套展开 │ hex dump │ 统计表格           │
├───────────────────────────────────────────────┤
│          类型解析层 (Pure Python)              │
│   .lcm 解析 → AST → fingerprint → 动态类生成   │
├───────────────────────────────────────────────┤
│           协议层 (Raw UDP Socket)              │
│     LCM Wire Protocol 解析（零依赖）            │
├───────────────────────────────────────────────┤
│           UDP 组播 (239.255.76.67)            │
└───────────────────────────────────────────────┘
```

- **零外部 LCM 依赖**：核心功能直接解析 UDP 组播数据包中的 LCM wire protocol
- **内置类型解析**：纯 Python 实现的 `.lcm` 文件解析器 + 运行时解码类生成器
- **节点发现**：通过 UDP 数据包的源 IP:port 推断不同发布者
- **传统解码兼容**：可选依赖 `lcm` Python 包，支持 `--type module.Class` 方式

## LCM 协议说明

LCM 使用 UDP 组播进行通信（默认 `239.255.76.67:7667`）。

**短消息**（< 64KB）：8 字节头 (magic=0x4c433032 + seqno) + channel name (\0结尾) + payload

**分片消息**：20 字节头 (magic=0x4c433033 + seqno + payload_size + fragment_offset + fragment_no + n_fragments)

参考：[LCM UDP Multicast Protocol](https://lcm-proj.github.io/lcm/content/udp-multicast-protocol.html)

## LCM 与 ROS2 概念映射

LCM 和 ROS2 有相似的发布/订阅通信模式，以下是概念对照：

| LCM 概念 | ROS2 对应 | 说明 |
|----------|----------|------|
| Channel | Topic | 消息发布/订阅的通道 |
| UDP (IP:port) | Node | LCM 无原生 node 概念，通过发布者地址推断 |
| Fingerprint | Message Type Hash | 消息类型的唯一标识 |

## 项目结构

```
src/lcm_cli/
├── __init__.py                  # 包定义 + 版本号
├── __main__.py                  # python -m lcm_cli 入口
├── cli.py                       # Typer 入口，注册子命令
├── commands/
│   ├── topic_echo.py            # lcm topic echo（支持 --csv/--jsonl 导出）
│   ├── topic_list.py            # lcm topic list（支持 --watch 模式）
│   ├── topic_stats.py           # lcm topic stats（支持 --sort/--top/--freeze/--spark）
│   ├── topic_bw.py              # lcm topic bw（带宽监控）
│   ├── topic_info.py            # lcm topic info（通道详细信息）
│   ├── node_list.py             # lcm node list（支持 --watch 模式）
│   ├── type_list.py             # lcm type list
│   ├── type_show.py             # lcm type show
│   ├── record.py                # lcm record
│   ├── play.py                  # lcm play
│   └── dashboard_cmd.py         # lcm dashboard（Web 仪表盘启动）
├── core/
│   ├── discovery.py             # 被动通道/节点发现
│   ├── stats.py                 # 实时统计（频率、带宽）
│   ├── lcm_type_parser.py       # .lcm 文件解析器 + fingerprint 算法
│   └── lcm_type_builder.py      # 运行时解码类生成 + TypeRegistry
├── dashboard/                   # Web 仪表盘（FastAPI + React + WebSocket）
│   ├── server.py                # FastAPI 应用：REST API + WebSocket 处理器
│   ├── data_bridge.py           # LCM 数据包 → WebSocket 数据桥接
│   ├── field_extractor.py       # 递归数值字段提取
│   ├── ring_buffer.py           # 按频道时间窗口缓存
│   ├── frontend/                # React + TypeScript + uPlot 前端
│   └── static/                  # 构建后的前端静态资源（由 FastAPI 提供服务）
├── display/
│   ├── echo_display.py          # Rich 面板显示（含递归嵌套展开）
│   ├── stats_display.py         # 统计表格显示（含 sparkline）
│   └── type_display.py          # 类型结构表格显示
├── export.py                    # 字段提取 + CSV/JSONL 写入器
├── lcm_log.py                   # LCM 日志文件读写器（兼容 lcm-logger）
├── listener.py                  # UDP 组播监听线程
├── protocol.py                  # LCM Wire Protocol 解析
└── source.py                    # PacketSource 抽象（实时/离线）
```

## 测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 网络配置

如果收不到消息，请检查组播路由：

**macOS:**
```bash
# 查看组播路由
netstat -rn | grep 239

# 添加路由（如果需要）
sudo route add -net 239.255.76.0/24 -interface en0
```

**Linux:**
```bash
# 添加路由
sudo ip route add 239.255.76.0/24 dev eth0
```

## 许可证

MIT
