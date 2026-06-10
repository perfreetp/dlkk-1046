# 🐾 Pet Namer - 宠物起名命令行工具

为宠物店店员和救助站志愿者批量生成待领养动物名字的专业工具。

## ✨ 功能特性

### 7大核心命令

| 命令 | 功能 |
|------|------|
| `generate` | 按多维度条件生成候选名字 |
| `filter` | 检查重复名和发音相近名 |
| `import` | 从表格文件批量导入宠物信息 |
| `favorite` | 管理收藏名字和设置正式名 |
| `rename` | 批量替换不合适的名字 |
| `export` | 导出领养海报名单（支持多种格式） |
| `stats` | 统计分析风格使用比例和数据 |

### 多维度筛选条件

- **物种**：猫、狗、兔子
- **性别**：公、母、中性
- **年龄**：按月龄范围筛选
- **毛色**：按毛发颜色匹配
- **性格标签**：活泼、温顺、安静、黏人等
- **来源批次**：按救助批次分组管理
- **名字长度**：最小/最大字符数
- **语言风格**：中文、英文，5种风格
- **禁用词**：过滤不合适的名字

### 名字风格

- 🎀 **可爱风 (cute)**：团子、棉花糖、Coco、Fluffy
- 🏮 **传统风 (traditional)**：来福、旺财、贝贝、多多
- 🌍 **欧美风 (western)**：Lucky、Bella、Max、Charlie
- 🎮 **酷炫风 (cool)**：闪电、悟空、雷神、Zeus
- 📚 **文艺风 (literary)**：明月、星辰、Luna、Aurora

## 📦 安装

```bash
pip install -e .
```

## 🚀 快速开始

### 1. 导入宠物信息

```bash
# 从CSV导入
pet-namer import examples/sample_pets.csv --batch 2024-06 --dry-run

# 从Excel导入
pet-namer import pets.xlsx --source "爱心救助站"
```

### 2. 生成名字

```bash
# 为所有未命名宠物生成5个候选名
pet-namer generate --all --count 5 --style cute

# 按条件筛选
pet-namer generate --species cat --gender female --language zh --style cute

# 按性格标签生成
pet-namer generate --personality 活泼 --personality 亲人 --coat-color 橘色

# 按名字长度筛选
pet-namer generate --min-length 2 --max-length 4

# 复现之前的生成结果
pet-namer generate --replay <记录ID>
```

### 3. 管理收藏和正式名

```bash
# 列出所有宠物及名字
pet-namer favorite --list

# 交互式选择正式名
pet-namer favorite --select

# 手动设置正式名
pet-namer favorite --set-name abc12345:团子

# 添加名字到收藏
pet-namer favorite --add abc12345:小橘
```

### 4. 检查问题名字

```bash
# 检查重复和发音相近
pet-namer filter

# 设置相似度阈值
pet-namer filter --threshold 0.8

# 自动修复重复名字
pet-namer filter --fix-duplicates

# 按批次检查
pet-namer filter --batch 2024-06-A
```

### 5. 批量替换名字

```bash
# 替换特定名字
pet-namer rename --from-name 豆豆 --to-name 团子

# 按模式替换
pet-namer rename --pattern "小*" --replace-with "大*"

# 按包含字符串替换
pet-namer rename --contains "旺财" --replace-with "来福"

# 列出问题名字
pet-namer rename --list-problems

# 替换后自动重新生成候选
pet-namer rename --from-name 旺财 --to-name 来福 --auto-regenerate
```

### 6. 导出领养海报

```bash
# 导出海报格式到文件
pet-namer export --format poster -o adoption_poster.txt

# 导出CSV
pet-namer export --format csv -o pets.csv --named-only

# 导出Excel
pet-namer export --format excel -o adoption_list.xlsx

# 包含候选名和收藏名
pet-namer export --format poster --include-candidates --include-favorites

# 按批次导出
pet-namer export --batch 2024-06-A --format poster
```

### 7. 统计分析

```bash
# 查看总体统计
pet-namer stats

# 显示生成记录历史
pet-namer stats --records

# 查看批次分布
pet-namer stats --by-batch

# 只显示TOP 5热门名字
pet-namer stats --top 5

# 导出统计数据
pet-namer stats -o stats.json
```

## 💾 数据存储

所有数据存储在 `--data-dir` 指定的目录（默认为 `.pet-namer`）：

- `pets.json` - 宠物信息
- `names.json` - 名字库
- `records.json` - 生成记录（可用于复现）
- `stats.json` - 统计数据
- `config.json` - 配置文件

## 🎯 工作流程示例

1. **导入**：从救助站表格导入10只猫咪的信息
2. **生成**：为每只猫咪生成5个可爱风中文候选名
3. **筛选**：检查是否有重复或发音相近的名字
4. **收藏**：人工选择合适的名字加入收藏
5. **确认**：为每只猫咪设置正式名
6. **检查**：再次运行filter确保所有名字唯一
7. **导出**：生成领养海报用于打印
8. **统计**：查看风格使用比例，优化后续生成策略

## 🧪 测试

```bash
# 测试示例导入
pet-namer import examples/sample_pets.csv --dry-run

# 测试生成（非交互式）
pet-namer generate --all --count 3 --no-interactive

# 测试统计
pet-namer stats
```

## 📁 项目结构

```
pet_namer/
├── __init__.py
├── __main__.py
├── cli.py              # CLI入口
├── models.py           # 数据模型
├── storage.py          # 数据存储
├── generator.py        # 名字生成引擎
├── name_library.py     # 名字库（150+名字）
└── commands/
    ├── generate.py     # 生成命令
    ├── filter.py       # 过滤命令
    ├── import_cmd.py   # 导入命令
    ├── favorite.py     # 收藏命令
    ├── rename.py       # 重命名命令
    ├── export.py       # 导出命令
    └── stats.py        # 统计命令
examples/
└── sample_pets.csv     # 示例数据
```

## 🤝 贡献

欢迎提交Issue和PR来扩展名字库或添加新功能！

## 📄 License

MIT License
