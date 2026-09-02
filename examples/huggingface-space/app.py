import shutil
import tempfile
import urllib.request
import uuid
from pathlib import Path

import gradio as gr
import numpy as np
import spaces
import torch
from PIL import Image
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor


CHECKPOINT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt"
CHECKPOINT = Path("/tmp/image-to-world-models/sam2.1_hiera_tiny.pt")
MODEL_CONFIG = "configs/sam2.1/sam2.1_hiera_t.yaml"


def _checkpoint():
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    if not CHECKPOINT.exists():
        temporary = CHECKPOINT.with_suffix(".download")
        urllib.request.urlretrieve(CHECKPOINT_URL, temporary)
        temporary.replace(CHECKPOINT)
    if CHECKPOINT.stat().st_size < 10_000_000:
        raise RuntimeError("SAM2 checkpoint download is incomplete")
    return CHECKPOINT


def _normalize(image):
    if image is None:
        raise gr.Error("Choose an image first.")
    source = Image.fromarray(np.asarray(image).astype(np.uint8)).convert("RGB")
    longest = max(source.size)
    if longest > 1024:
        scale = 1024 / longest
        source = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
    return source


@spaces.GPU(duration=60)
def segment(image, points_per_side=16, pred_iou_thresh=0.8, focus_x=-1, focus_y=-1):
    source = _normalize(image)
    model = build_sam2(MODEL_CONFIG, str(_checkpoint()), device="cuda")
    generator = SAM2AutomaticMaskGenerator(
        model,
        points_per_side=int(points_per_side),
        pred_iou_thresh=float(pred_iou_thresh),
    )
    try:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            records = generator.generate(np.asarray(source))
            if 0 <= float(focus_x) < source.width and 0 <= float(focus_y) < source.height:
                predictor = SAM2ImagePredictor(model)
                predictor.set_image(np.asarray(source))
                masks, scores, _ = predictor.predict(
                    point_coords=np.asarray([[float(focus_x), float(focus_y)]], dtype=np.float32),
                    point_labels=np.asarray([1], dtype=np.int32),
                    multimask_output=True,
                )
                def focus_quality(mask):
                    ys, xs = np.where(mask)
                    if not len(xs):
                        return 0.0
                    bbox_area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
                    area = float(mask.sum())
                    return area * (area / bbox_area)

                best = max(range(len(masks)), key=lambda index: focus_quality(masks[index]))
                records.append({"segmentation": masks[best]})
        output = Path(tempfile.mkdtemp(prefix="image-to-world-sam2-"))
        for index, record in enumerate(records):
            mask = np.asarray(record["segmentation"], dtype=np.uint8) * 255
            Image.fromarray(mask, "L").save(output / f"raw_{index:03d}.png")
        if not records:
            raise gr.Error("SAM2 returned zero masks.")
        archive_base = Path("/tmp/image-to-world-results") / f"masks-{uuid.uuid4().hex}"
        archive_base.parent.mkdir(parents=True, exist_ok=True)
        archive = shutil.make_archive(str(archive_base), "zip", root_dir=output)
        return archive
    finally:
        del generator
        del model
        torch.cuda.empty_cache()


with gr.Blocks(title="Image to World SAM2") as demo:
    gr.Markdown("# Image to World SAM2\nGenerate raw automatic masks for the image-to-world pipeline.")
    with gr.Row():
        image_input = gr.Image(type="numpy", label="Source image")
        archive_output = gr.File(label="Mask ZIP")
    with gr.Row():
        points_input = gr.Slider(8, 32, value=16, step=4, label="Points per side")
        threshold_input = gr.Slider(0.5, 0.99, value=0.8, step=0.01, label="Predicted IoU threshold")
    with gr.Row():
        focus_x_input = gr.Number(value=-1, label="Optional focus X")
        focus_y_input = gr.Number(value=-1, label="Optional focus Y")
    run_button = gr.Button("Segment", variant="primary")
    run_button.click(
        segment,
        inputs=[image_input, points_input, threshold_input, focus_x_input, focus_y_input],
        outputs=archive_output,
        api_name="segment",
    )


if __name__ == "__main__":
    demo.queue().launch()
