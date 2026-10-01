# Aligned Raster Algebra

离线栅格地图代数工具（仅 Python 标准库，要求 Python 3.12+）。读取一个 JSON
任务文件，把多个不同范围的矩形网格按公共格网对齐，逐格执行表达式，并输出
完整结果矩阵、缺失数据坐标与统计信息。

## 用法

```bash
python -m raster_algebra task.json result.json
```

- 成功：写出结果 JSON，退出码 `0`。
- 任务非法：向标准错误打印原因，退出码非零，且**不产生结果文件**。

## 任务 JSON

```json
{
  "mode": "intersection",
  "grids": {
    "a": {
      "origin": [0, 0],
      "cell_size": 10,
      "data": [[1, 2, null], [4, null, 6]]
    },
    "b": {
      "origin": [10, 10],
      "cell_size": 10,
      "data": [[10, null], [null, 40]]
    }
  },
  "expression": "a + coalesce(b, 0)"
}
```

### 网格定位规则

- `origin` 为左上角整数坐标 `[x, y]`，列向右、行向下，坐标可为负数。
- `cell_size` 为正整数；所有网格格宽必须相同，不做重采样或插值。
- 各网格原点之差必须是 `cell_size` 的整数倍，否则任务被拒绝。
- `data` 必须是非空矩形矩阵；每个格为有限数字（整数或浮点数）或 `null`；
  空矩阵、行长不齐、布尔值、`NaN`/`Infinity` 均被拒绝。

### 范围

- `"intersection"`（默认）：输出所有网格共同覆盖的范围；无交集时报错。
- `"union"`：输出覆盖所有网格的最小包围矩形；网格外的位置按 `null` 处理。

## 表达式

手写递归下降解析器，**不会执行表达式携带的任何代码**。允许：

- 数字字面量、网格名称、括号；
- 四则运算 `+ - * /` 与一元正负号；
- `coalesce(expr, expr, ...)`：至少一个参数，按顺序返回首个非空值。

语义：

- 普通二元运算的两侧**都会求值**；任一操作数为 `null`，结果为 `null`。
- 除零或结果非有限（溢出为 ±∞/NaN）时结果为 `null`，并把该输出格坐标
  记入 `invalid_cells`；因操作数为 `null` 而传播的空值**不**记入。
- `coalesce` 短路求值：命中首个非空参数后立即停止；被回退拯救的格不算
  非法格。若所有参数均为 `null`，且某个已求值参数发生过除零/非有限，
  则该格记入 `invalid_cells`。
- 禁止属性访问（`a.b`）、下标（`a[0]`）、`coalesce` 以外的调用、
  幂运算、关键字/逻辑运算等；引用未定义的网格名称同样报错。
- 结果与 `grids` 中键的书写顺序无关。

## 结果 JSON

```json
{
  "origin": [10, 10],
  "cell_size": 10,
  "data": [[11]],
  "invalid_cells": [],
  "stats": {
    "valid_count": 1,
    "null_count": 0,
    "min": 11.0,
    "max": 11.0,
    "mean": 11.0
  }
}
```

- `origin`：输出矩阵左上角的世界坐标；`data` 为完整矩阵（行优先）。
- `invalid_cells`：`[row, column]`，均为相对于输出矩阵原点的 0 基索引。
- `stats`：有效格数、空值数，以及有效值的 `min`/`max`/`mean`；
  全为空时三个统计值均为 `null`。

## 测试

```bash
python -m unittest discover -s tests
```

覆盖：负坐标、错位原点拒绝、格宽不一致、空交集、空矩阵/行长不齐/非法值、
除零与非有限记录、`null` 传播、`coalesce` 回退与未求值分支、网格顺序无关、
统计以及 CLI 成功/失败退出码。
