# HTML 实体解码修复 - 实施总结

## 问题描述

RSS 抓取流程中没有对 HTML 实体进行解码，导致数据库和上传到 memos 的内容包含大量 HTML 实体编码（如 `&#8217;`、`&#8220;`、`&#8212;` 等）。

## 实施方案

采用了 **方案 C：完整方案 + 增强修复**，包含以下改进：

### 1. ✅ fetcher.py 源头解码（迭代解码）

在 `extract_article_content` 函数中添加**迭代** HTML 实体解码：

- 对 RSS `content` 字段解码
- 对 RSS `summary` 字段解码
- **处理双重编码场景**（如 `&amp;nbsp;` → `&nbsp;` → 空格）
- **处理命名实体**（如 `&nbsp;`、`&copy;` 等）

**修改文件：**
- `fetcher.py`: 添加 `_iterative_unescape()` 函数，使用迭代解码

### 2. ✅ storage.py 双重保险（迭代解码）

在 `save_article` 函数中添加**迭代** HTML 实体解码：

- 使用迭代解码处理双重编码
- 确保数据库中存储的是完全解码后的内容

**修改文件：**
- `storage.py`: 添加 `_iterative_unescape()` 函数

### 3. ✅ 数据迁移脚本（增强版）

更新 `migrate_decode_entities.py` 脚本：

- **扩展检测规则**：包含命名实体（`&nbsp;`、`&copy;` 等）
- **迭代解码**：处理双重编码场景
- 支持干运行模式（`--dry-run`）预览变更

**修改文件：**
- `migrate_decode_entities.py`: 扩展 `HTML_ENTITY_PATTERNS`，添加 `iterative_unescape()`

## 测试覆盖

所有修改都遵循 TDD 流程，测试覆盖：

- **fetcher.py**: 9 个测试
  - RSS content 字段解码
  - RSS summary 字段解码
  - 常见 HTML 实体解码
  - 混合实体解码
  - 数字实体解码
  - 空内容处理
  - **双重编码解码**（新增）
  - **三重编码解码**（新增）
  - **命名实体解码**（新增）

- **storage.py**: 6 个测试
  - 存储 HTML 实体解码
  - 常见实体解码
  - 空内容处理
  - 重复 URL 处理
  - **命名实体解码**（新增）
  - **双重编码解码**（新增）

- **migrate_decode_entities.py**: 8 个测试
  - HTML 实体检测
  - 统计功能
  - 迁移功能
  - 干运行模式
  - 所有常见实体处理
  - **命名实体检测**（新增）
  - **命名实体迁移**（新增）
  - **双重编码迁移**（新增）

**总计：23 个测试，全部通过 ✅**

## 修复结果

### 第一次迁移
- 处理 96 篇文章，主要清除 `&#8217;`、`&#8220;` 等数字实体
- 遗漏 6 篇包含命名实体的文章

### 第二次迁移（增强后）
- 处理 6 篇文章，清除 `&nbsp;` 等命名实体和双重编码
- **最终状态：所有 HTML 实体完全清除** ✅

### 验证结果
```
✓ 数字实体 (&#...): 0 篇
✓ 命名实体 (&nbsp; 等): 0 篇
✓ 无 &amp; 或 &nbsp; 残留
✓ 所有 HTML 实体都已清除！
```

## 使用方法

### 运行数据迁移

```bash
# 1. 先预览会迁移哪些文章
python migrate_decode_entities.py --dry-run

# 2. 确认无误后执行实际迁移
python migrate_decode_entities.py
```

### 验证效果

运行测试确保所有功能正常：

```bash
./.venv/bin/python -m pytest tests/ -v
```

## 技术细节

### 迭代解码算法

```python
def _iterative_unescape(text: str, max_iterations: int = 5) -> str:
    """迭代解码 HTML 实体，直到内容稳定"""
    result = text
    for _ in range(max_iterations):
        unescaped = html.unescape(result)
        if unescaped == result:
            break
        result = unescaped
    return result
```

**处理场景：**
- 单次编码：`&amp;` → `&`
- 双重编码：`&amp;amp;` → `&amp;` → `&`
- 三重编码：`&amp;amp;amp;` → `&amp;amp;` → `&amp;` → `&`

### 支持的实体格式

- **命名实体**：`&amp;`、`&nbsp;`、`&copy;`、`&reg;`、`&trade;`、`&euro;`、`&pound;`、`&yen;`、`&hellip;`、`&lt;`、`&gt;`、`&quot;`、`&apos;`
- **数字实体**：`&#8217;`、`&#8220;`、`&#8212;`、`&#8230;`、`&#36;` 等

## 注意事项

- 解码是幂等的：已解码的内容再次解码不会有副作用
- 迭代有最大次数限制（5 次），防止无限循环
- 正常的 `#数字` 文本（如 `#1 排名`、`#ff0000` 颜色值）不会被误删除
