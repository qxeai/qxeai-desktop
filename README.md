# qxeai-desktop
制作自己的 Ai 模型
> QXEAi 创建的初衷是供代码研究使用。二次分发时请遵守 [LICENSE](./LICENSE)
### 特性
- 通过知识库创建自己的Ai 模型
- 通过导出 `.qxeai` 模型文件以供使用
### 要求
- Python 3.10 +
### 使用
1.拉取仓库

2.安装依赖
```python
pip install -r requirements.txt
```
3.运行
```python
python main.py
```
### 知识库
仓库内置了 `ai-skills-prompt.txt`。通过使用这个提示词，您就能得到知识库`.json`文件
- [Here is prompt](./ai-skills-prompt.txt)
### 打包
1.安装`Pyinstaller`通过pip

2.定位仓库目录

3.构建(Windows)
```pyinstaller
pyinstaller --noconfirm --onefile --windowed --name QXEAi --collect-all jieba --hidden-import jieba --hidden-import rapidfuzz main.py
```
