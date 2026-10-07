"""ComfyUI-DJ_ImageExpand 入口：图像扩展编辑器（裁剪 + 旋转 + 扩展画布）。

清洗自 AusBoss 的 Image Crop + Rotate + Pad 节点（2026-07-17），
只保留这一个节点，默认填充色 #414100（0.255.0）。

坑位：
- 每个节点文件自带 NODE_CLASS_MAPPINGS / NODE_DISPLAY_NAME_MAPPINGS，
  这里只做合并；新增节点把模块名加进 NODE_MODULES 即可。
- 导入失败的模块只打警告、不拖垮整个包。
"""

import importlib
import traceback

NODE_MODULES = [
    "node_image_crop_rotate_pad",
]

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
_failed_modules = []

for _module_name in NODE_MODULES:
    try:
        _module = importlib.import_module(f".nodes.{_module_name}", __name__)
        NODE_CLASS_MAPPINGS.update(getattr(_module, "NODE_CLASS_MAPPINGS", {}))
        NODE_DISPLAY_NAME_MAPPINGS.update(
            getattr(_module, "NODE_DISPLAY_NAME_MAPPINGS", {})
        )
    except Exception:
        _failed_modules.append(_module_name)
        traceback.print_exc()

# 浏览器加载的前端目录；里面每个 .js 都按扩展加载，.mjs 只供 import。
WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]


def _print_banner():
    # 纯 ASCII：Windows 上 ComfyUI 控制台常是 cp1252，Unicode 会炸掉整个包。
    print("-" * 60)
    print(f"  DJ ImageExpand | {len(NODE_CLASS_MAPPINGS)} nodes loaded")
    if _failed_modules:
        print(f"  Failed to load: {', '.join(_failed_modules)}")
    print("-" * 60)


_print_banner()
