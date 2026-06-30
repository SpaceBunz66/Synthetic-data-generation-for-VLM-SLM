# Synthetic Manga/Game Data Pipeline

Pipeline này tạo synthetic data cho hai domain `manga` và `game`, phục vụ fine-tune SLM/VLM cho các task OCR, translation và structured VLM output.

Generator có thể chạy hoàn toàn offline bằng rule-based content generator, hoặc gọi API Gemini/Groq/OpenAI để tăng độ phong phú của text. Output luôn được chuẩn hóa về cùng một canonical annotation rồi export ra `vlm`, `ocr`, `trans` và `chat_vlm.jsonl`.

## 1. Cài Đặt

Yêu cầu Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`playwright` là dependency optional cho HTML/CSS game renderer. Nếu muốn dùng renderer browser thay vì fallback Pillow:

```powershell
python -m playwright install chromium
```

Nếu không cài Chromium, `--game-renderer auto` sẽ tự fallback về Pillow và pipeline vẫn chạy được.

## 2. Data Local Và Git Ignore

Các folder lớn sau được `.gitignore` để repo nhẹ:

```text
data/raw/
data/example_json_output/
data/generated/
```

Việc ignore hai folder `data/raw/` và `data/example_json_output/` không ảnh hưởng đến rule-based generator, content rules, renderer, augmentation, exporter hoặc validation chính.

Ảnh hưởng cụ thể:

- `data/raw/`: optional local dataset dùng để tham khảo domain gap hoặc phát triển thêm asset/domain adaptation. Code synthetic hiện tại không đọc trực tiếp folder này.
- `data/example_json_output/`: optional fixtures/schema examples. Test sẽ tự skip phần này nếu folder không tồn tại.
- `data/generated/`: output sinh ra từ pipeline, không nên commit.

Bạn không cần xóa `data/raw/` ở máy local. Chỉ cần để nó bị ignore để không upload lên Git.

Khuyến nghị cấu trúc local:

```text
data/
  raw/
    manga/
      train/
      valid/
      test/
    game/
      train/
      valid/
      test/
  example_json_output/
    vlm.json
    ocr.json
    trans.json
    image2.png
```

Người dùng khác có thể tự tải hoặc tự đặt bộ data riêng vào `data/raw/`. Pipeline hiện tại không hard-code việc đọc raw data, nên dataset riêng không làm hỏng generator.

## 3. Generate Một Batch Nhỏ

Chạy offline bằng fallback generator:

```powershell
python scripts/generate_synthetic_dataset.py --output data/generated/synthetic_poc --count 20 --seed 1337 --clean
```

Output sẽ nằm trong:

```text
data/generated/synthetic_poc/
  images/
  annotations/
    canonical/
    vlm/
    ocr/
    trans/
    vlm.jsonl
    ocr.jsonl
    trans.jsonl
  cache/content/
  chat_vlm.jsonl
  manifest.jsonl
  summary.json
```

## 4. Các Option Quan Trọng

```powershell
python scripts/generate_synthetic_dataset.py `
  --output data/generated/synthetic_poc `
  --count 100 `
  --seed 2026 `
  --clean `
  --game-renderer auto `
  --blocks-per-sample 5
```

Dense mode for harder VLM/OCR samples:

```powershell
python scripts/generate_synthetic_dataset.py `
  --output data/generated/synthetic_dense `
  --count 100 `
  --seed 2026 `
  --clean `
  --difficulty dense
```

Option chính:

- `--count`: số ảnh cần sinh.
- `--seed`: seed deterministic.
- `--clean`: xóa output cũ trước khi sinh lại.
- `--no-augment`: tắt augmentation để debug dễ hơn.
- `--no-progress`: tắt thanh loading/ETA khi cần log sạch.
- `--difficulty normal|dense`: `normal` giữ layout cũ; `dense` dùng layout procedural dày hơn với nhiều text/bbox hơn.
- `--game-renderer auto|playwright|pillow`: `auto` thử Playwright trước, fallback Pillow.
- `--blocks-per-sample`: số block text semantic trước khi wrap thành line-level bbox; mặc định là 5 cho `normal`, 12 cho `dense`.
- `--content-provider fallback|gemini|groq|openai`: nguồn sinh text.
- `--content-model`: model API muốn dùng.
- `--api-timeout`: timeout cho API call.

`dense` vẫn giữ annotation chuẩn xác bằng cách render procedural bằng Pillow/HTML, không dùng diffusion/text-to-image.
Manga dùng nhiều layout panel bất đối xứng, panel-local scan/screentone noise, color clutter và procedural panel art như nhân vật, cảnh nền, vật thể, dáng hành động được đặt tránh bubble text; game dùng nhiều scene style như dialogue screenshot, floating nameplates, crafting/menu, battle arena, vendor shop, map screen, party status và HUD overlay.

## 5. Dùng Gemini Hoặc Groq

Gemini:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
python scripts/generate_synthetic_dataset.py `
  --output data/generated/gemini_poc `
  --count 20 `
  --clean `
  --content-provider gemini `
  --content-model gemini-2.0-flash
```

Groq:

```powershell
$env:GROQ_API_KEY="YOUR_KEY"
python scripts/generate_synthetic_dataset.py `
  --output data/generated/groq_poc `
  --count 20 `
  --clean `
  --content-provider groq `
  --content-model llama-3.1-8b-instant
```

Nếu thiếu key hoặc API lỗi, pipeline không dừng hẳn. Nó fallback sang generator offline và ghi lỗi vào `cache/content/*.json`.

## 6. Content Rules

Default generator áp dụng các rule:

- Một ảnh chỉ có một source language.
- Chỉ dùng source language `en`; `translated_text` vẫn là bản dịch tiếng Việt.
- Không sinh SFX/action-word như boom, bang, crash, rầm, ầm.
- Manga chỉ dùng speech/narration, không có quest/HUD/menu.
- Game dùng RPG UI/dialog/HUD/menu/floating label.
- Ground truth vẫn là line-level bbox giống sample hiện tại.

## 7. Validate Output

```powershell
python scripts/validate_synthetic_dataset.py data/generated/synthetic_poc
```

Validator kiểm tra:

- Ảnh tồn tại.
- BBox nằm trong ảnh và có diện tích hợp lệ.
- `vlm`, `ocr`, `trans`, `canonical` nhất quán line count.
- `chat_vlm.jsonl` parse được và assistant JSON khớp `vlm`.
- Không mixed language trong cùng ảnh.
- Không leak `sfx`/action-word.
- Manga không leak game terms.

## 8. Chạy Test

```powershell
python -m unittest discover -s tests -v
```

Nếu `data/example_json_output/` không tồn tại, test schema fixture sẽ được skip. Các test core của generator vẫn chạy bình thường.

## 9. Output Formats

`annotations/vlm/<id>.json`:

```json
{
  "category": "manga",
  "content": [
    {
      "bbox_2d": [10, 20, 120, 48],
      "text": "example text",
      "translated_text": "bản dịch tiếng Việt"
    }
  ]
}
```

`annotations/ocr/<id>.json`:

```json
[
  {
    "bbox_2d": [10, 20, 120, 48],
    "text": "example text"
  }
]
```

`annotations/trans/<id>.json`:

```json
[
  {
    "id": 1,
    "text": "example text",
    "translated_text": "bản dịch tiếng Việt"
  }
]
```

`chat_vlm.jsonl` chứa image path, instruction, và assistant response JSON để dùng cho fine-tune SLM/VLM.
