# Image Crossword Collage

这是一个开源 Codex skill 与确定性图像排版器，可把用户照片转成个性化的时尚编辑式填字拼贴。

它把工作分成两层：视觉模型负责理解图像、选择与画面有关的词语并标记位置；Python 渲染器负责网格、文字、半透明色块、图像面板和最终导出。这样既能保证字形准确，也能让不同用户的结果与各自输入强相关。

## 特点

- `photo-overlay`：保留单张照片的完整视觉身份，在其上添加交叉文字和彩色方块。
- `grid-board`：在米白色网格上组织一张或多张图片，适合物件、穿搭和 lookbook。
- 输入图片字节、语义配置和 `variant` 共同决定种子：同参数可复现，换图或换 variant 会改变布局。
- `grid_style: random` 会根据同一个种子稳定地选择完整网格或无背景网格；也可以用 `full` / `none` 强制指定。
- 中英文均可渲染；最终文字由代码绘制，不依赖图像模型生成文字。
- 本地渲染脚本不联网，也不收集数据。

仓库不包含用户提供的参考图或照片。

## 安装到 Codex

把整个仓库放到：

```text
~/.codex/skills/image-crossword-collage
```

然后上传图片并使用：

```text
使用 $image-crossword-collage 把这张照片生成个性化的编辑式填字拼贴。
```

独立运行 Python 脚本时，先安装依赖：

```bash
python3 -m pip install -r requirements.txt
python3 scripts/render_crossword_collage.py \
  --input /图片的绝对路径.jpg \
  --spec examples/example-spec.json \
  --output result.png
```

完整配置字段见 [references/spec.md](references/spec.md)，开发与贡献方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目使用 [MIT License](LICENSE)。
