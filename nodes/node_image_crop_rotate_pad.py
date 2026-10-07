"""图像扩展编辑器：加载图片，做旋转、裁剪、扩展画布（outpaint 底图）。

清洗自 AusBoss 的 Image Crop + Rotate + Pad 节点（2026-07-17），功能未动。
默认填充色 #414100（RGB 65,65,0，即 0.255.0）。
"""

from __future__ import annotations

from ._media_helpers import list_input_images, load_image_frames, resolve_input_path
from ._inpaint_crop_helpers import build_transform_stitcher
from ._transform_engine import (
    original_image_batch,
    resize_batch_to_megapixels,
    resize_image_batch,
    stable_file_fingerprint,
    transform_pil_batch,
)
from ._transform_inputs import resize_inputs, spec_from_values, transform_inputs


class ImageExpand_DJ:
    CATEGORY = "DJ/ImageExpand"
    DESCRIPTION = (
        "加载图片并执行一次旋转、裁剪、扩展画布变换。"
        "蒙版标记需要绘制的区域：新增填充边距、旋转留下的空角、以及图片中透明的部分（不透明度低于 90%），"
        "这些部分按填充色处理。可选将结果缩放到指定百万像素预算"
        "（核心 Scale Image to Total Pixels 语义：保持宽高比，尺寸取整到 resolution_steps）。"
    )
    SEARCH_ALIASES = ["image crop", "rotate image", "pad image", "outpaint canvas", "djimageexpand"]

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "image": (
                list_input_images(),
                {"image_upload": True, "tooltip": "Choose or upload an image from ComfyUI's input folder."},
            )
        }
        required.update(transform_inputs())
        # Appended AFTER the stable V1 widgets, so saved workflows' positional
        # widgets_values keep loading, and optional, so an API prompt from
        # before they existed still validates; missing values fall back to
        # load_transform's defaults. The stitch settings come last, as on
        # the clip node: older saved workflows and API prompts keep the
        # 32 px blend they always had.
        optional = resize_inputs()
        optional.update({
            "stitch_blend": (
                "INT",
                {
                    "default": 32,
                    "min": 0,
                    "max": 512,
                    "step": 1,
                    "tooltip": (
                        "Ramp of the stitcher's paste, in pixels, into the kept "
                        "picture: where generated pixels fade over the source. "
                        "Separate from feather, which shapes the mask itself."
                    ),
                },
            ),
            "stitch_grow": (
                "INT",
                {
                    "default": 0,
                    "min": -256,
                    "max": 256,
                    "step": 1,
                    "tooltip": (
                        "Moves the paste boundary before the ramp: positive lets "
                        "the generation replace a strip of the source next to "
                        "the seam, negative keeps more of the source."
                    ),
                },
            ),
        })
        return {"required": required, "optional": optional}

    # Appended outputs only: saved links ride slot indices.
    # RETURN_NAMES 用中文显示名（2026-07-18 按用户要求）；槽位顺序不动，
    # 已保存工作流的连线靠槽位索引挂载，改名不影响旧流程。
    RETURN_TYPES = ("IMAGE", "MASK", "DJ_IMAGEEXPAND_STITCHER", "IMAGE", "INT", "INT", "IMAGE")
    RETURN_NAMES = ("图像", "蒙版", "缝合器", "原图", "宽度", "高度", "提示图")
    OUTPUT_TOOLTIPS = (
        "变换后的图像批次（BHWC 格式）。",
        "白色区域为模型需要绘制的部分：填充边距、旋转留下的空角、以及图片中透明的部分。",
        "全画布缝合器：在扩图结果上恢复保留的源图像素；接到 Stitch Inpaint 节点使用。",
        "旋转、裁剪、填充或缩放之前的原图。透明部分显示为白色。",
        "变换及缩放后的输出宽度。",
        "变换及缩放后的输出高度。",
        "将透明部分显示为白底（而非填充色）的图像。接到写提示词的节点，让抠图获得真实背景；"
        "若图片没有透明部分，则与「图像」输出相同。",
    )
    FUNCTION = "load_transform"

    def load_transform(
        self,
        image: str,
        resize_to_megapixels=False,
        megapixels=1.0,
        resize_method="lanczos",
        resolution_steps=1,
        stitch_blend=32,
        stitch_grow=0,
        **values,
    ):
        path = resolve_input_path(image)
        frames = load_image_frames(path)
        output, mask, geometry, prompt_image = transform_pil_batch(
            frames, spec_from_values(**values), view=True
        )
        if resize_to_megapixels:
            output, mask = resize_batch_to_megapixels(
                output, mask, float(megapixels), str(resize_method), int(resolution_steps)
            )
            if prompt_image is not None:
                prompt_image = resize_image_batch(
                    prompt_image, int(output.shape[2]), int(output.shape[1]), str(resize_method)
                )
        stitcher = build_transform_stitcher(
            output, mask, geometry, int(stitch_blend), int(stitch_grow),
            source="图像扩展编辑器",
        )
        # Nothing see-through: the prompt view is the image itself, as a copy
        # so no consumer can change one through the other.
        if prompt_image is None:
            prompt_image = output.clone()
        return (
            output, mask, stitcher, original_image_batch(frames),
            int(output.shape[2]), int(output.shape[1]), prompt_image,
        )

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        # ComfyUI skips its own range and list checks for every input named
        # here and files a failure once per named input, so only the source
        # is named. Its list check would refuse uploads it has not listed yet
        # and MaskEditor saves ("... [input]"); resolve_input_path takes any
        # file inside the input folder instead, and nothing outside it.
        try:
            resolve_input_path(image)
        except Exception as exc:
            return f"图像扩展编辑器: {exc}"
        return True

    @classmethod
    def IS_CHANGED(cls, image, **values):
        try:
            path = resolve_input_path(image)
        except Exception:
            path = image or ""
        spec = spec_from_values(**values)
        # Every widget value is already part of ComfyUI's cache key, so a
        # changed transform or budget re-runs the node without this; the
        # fingerprint's job is noticing the image file change on disk. The
        # resize values live outside TransformSpec and ride along beside it.
        resize = {name: values.get(name) for name in resize_inputs()}
        return stable_file_fingerprint(path, {"image": image, **spec.__dict__, **resize})


NODE_CLASS_MAPPINGS = {"ComfyUI-DJ_ImageExpand": ImageExpand_DJ}
NODE_DISPLAY_NAME_MAPPINGS = {"ComfyUI-DJ_ImageExpand": "ComfyUI-DJ_ImageExpand_图像扩展编辑器"}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

