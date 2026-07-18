from __future__ import annotations

import base64
import html
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
import zlib
from pathlib import Path

from . import shared as _shared

for _name in dir(_shared):
    if _name.startswith("_"):
        globals()[_name] = getattr(_shared, _name)

DLC_ID = 'core.short_video'
DLC_PROTOCOL = 'CF-FARP@0.4'
TOOLS = ['generate_short_video']

def _build_short_video_project(idea: str, title: str, topic: str, style: str, audience: str, duration: int, plan_text: str = "") -> dict:
    idea = _clean_spoken_text(idea)
    title = _clean_spoken_text(title) or _generate_video_title(idea, style)
    topic = _clean_spoken_text(topic) or _expand_video_topic(idea, style)
    style = _clean_spoken_text(style) or _infer_video_style(idea)
    if style == "自动匹配":
        style = _infer_video_style(idea)
    audience = _clean_spoken_text(audience)
    plan = _parse_video_plan(plan_text)
    if plan.get("title") and not title:
        title = _clean_spoken_text(plan["title"])
    if plan.get("topic") and not topic:
        topic = _clean_spoken_text(plan["topic"])

    scene_count = 3 if duration <= 10 else 4 if duration <= 25 else 5
    scene_duration = max(1, duration // scene_count)
    keywords = _extract_keywords(f"{idea} {topic}")
    keyword_a = keywords[0] if keywords else title[:10]
    keyword_b = keywords[1] if len(keywords) > 1 else keyword_a
    narrations = _scene_narrations(idea, title, topic, style, scene_count, plan)
    onscreen_texts = _scene_onscreen_texts(title, topic, keywords, scene_count)
    angles = ["开场", "问题", "转折", "方法", "结尾"]
    palettes = [
        ("#111827", "#f97316", "#fef3c7"),
        ("#0f172a", "#22c55e", "#dcfce7"),
        ("#1f2937", "#38bdf8", "#e0f2fe"),
        ("#18181b", "#eab308", "#fef9c3"),
        ("#312e81", "#fb7185", "#ffe4e6"),
    ]
    scenes = []
    for index in range(scene_count):
        start = index * scene_duration
        end = duration if index == scene_count - 1 else min(duration, start + scene_duration)
        bg, accent, soft = palettes[index % len(palettes)]
        scenes.append({
            "index": index + 1,
            "start": start,
            "end": end,
            "title": f"{angles[index]}：{onscreen_texts[index]}",
            "visual_prompt": _scene_visual_prompt(style, topic, keyword_a, keyword_b, index),
            "narration": narrations[index],
            "voiceover": narrations[index],
            "onscreen_text": onscreen_texts[index],
            "subtitle": narrations[index],
            "palette": {"background": bg, "accent": accent, "soft": soft},
        })
    return {
        "title": title,
        "idea": idea,
        "topic": topic,
        "style": style,
        "audience": audience or "自动推断",
        "duration_seconds": duration,
        "format": {"width": 360, "height": 640, "fps": 10},
        "seed": int(hashlib.sha256(f"{idea}|{title}|{topic}|{style}|{audience}".encode("utf-8")).hexdigest()[:8], 16),
        "scenes": scenes,
        "integrations": {
            "image": {"provider": "local", "status": "fallback", "outputs": []},
            "tts": {"provider": "local", "status": "fallback", "output": ""},
            "video": {"provider": "local_avi", "status": "fallback", "output": ""},
        },
        "notes": "短视频产物包：只需输入一个想法，系统自动补标题、文案、分镜、字幕和配音。配置 OPENAI_API_KEY 会尝试真实图片与 TTS；安装 FFmpeg 后会输出带音频的 MP4，否则输出带字幕 AVI 与独立 WAV。",
    }

def _extract_keywords(text: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"[\s,，。！？!?:：；;、|/\\（）()《》\"']+", text) if item.strip()]
    keywords = []
    for item in parts:
        if len(item) > 18:
            chunks = [item[i:i + 8] for i in range(0, min(len(item), 32), 8)]
        else:
            chunks = [item]
        for chunk in chunks:
            if chunk and chunk not in keywords:
                keywords.append(chunk)
            if len(keywords) >= 6:
                return keywords
    return keywords

def _clean_spoken_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    text = re.sub(r"[\\`*_#{}\[\]<>|]+", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return text.strip(" \"'，。；;、")

def _generate_video_title(idea: str, style: str) -> str:
    clean = _clean_spoken_text(idea)
    keywords = _extract_keywords(clean)
    if any(word in clean for word in ["赌", "上瘾", "失控", "成瘾"]):
        if "赌徒" in clean:
            return "赌徒的一生：从第一次到停下来"
        if "赌博" in clean:
            return "赌博失控前的几个信号"
        return f"{keywords[0] if keywords else '失控'}：从第一次到停下来"
    if any(word in clean for word in ["README", "readme", "文档"]):
        return "把项目说明写清楚"
    if any(word in clean for word in ["日志", "报错", "诊断"]):
        return "快速定位问题根因"
    if len(clean) <= 18:
        return clean
    first = re.split(r"[，。！？!?,；;]", clean)[0].strip()
    return first[:24] or "一条自动生成的短视频"

def _expand_video_topic(idea: str, style: str) -> str:
    clean = _clean_spoken_text(idea)
    if any(word in clean for word in ["赌", "上瘾", "失控", "成瘾"]):
        return f"{clean}。重点讲清楚诱惑、加码、失控和及时止损，让观众看到风险链条。"
    if "CSV" in clean.upper():
        return f"{clean}。重点展示从数据整理到结论提炼，再到报告输出的完整过程。"
    if any(word in clean for word in ["产品", "发布", "功能"]):
        return f"{clean}。重点说明用户痛点、核心能力、使用场景和下一步行动。"
    return f"{clean}。用具体场景开头，中段讲清楚关键转折，结尾给出明确结论。"

def _infer_video_style(idea: str) -> str:
    clean = _clean_spoken_text(idea)
    if any(word in clean for word in ["赌", "风险", "警示", "骗局", "失控"]):
        return "警示故事"
    if any(word in clean for word in ["教程", "怎么", "如何", "步骤"]):
        return "教程讲解"
    if any(word in clean for word in ["产品", "发布", "卖点"]):
        return "产品发布"
    return "知识科普"

def _parse_video_plan(plan_text: str) -> dict:
    text = str(plan_text or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    title_match = re.search(r"(?:标题|title)\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
    narrations = re.findall(r"(?:旁白|narration|voiceover)\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
    result = {}
    if title_match:
        result["title"] = title_match.group(1).strip()
    if narrations:
        result["narrations"] = [_clean_spoken_text(item) for item in narrations if _clean_spoken_text(item)]
    return result

def _scene_narrations(idea: str, title: str, topic: str, style: str, scene_count: int, plan: dict) -> list[str]:
    planned = plan.get("narrations") if isinstance(plan.get("narrations"), list) else []
    cleaned = [_clean_spoken_text(item) for item in planned if _clean_spoken_text(str(item))]
    if len(cleaned) >= scene_count:
        return cleaned[:scene_count]

    keywords = _extract_keywords(f"{idea} {topic}")
    key = keywords[0] if keywords else title
    second = keywords[1] if len(keywords) > 1 else key
    if style == "警示故事":
        if any(word in idea for word in ["赌", "下注", "上瘾"]):
            key = "下注"
            second = "失控"
        lines = [
            f"{title}，真正可怕的不是一次选择，而是你以为自己随时能停。",
            f"第一次只是试一下，第二次想赢回来，{key}就是这样一步步变成习惯。",
            f"当人开始加码、隐瞒、借口越来越多，问题已经不是输赢，而是失控。",
            f"能停下来的关键，是承认风险，切断入口，并找一个现实中的人一起监督。",
            f"别等到底线被击穿才回头，现在停下来，就是重新拿回生活的开始。",
        ]
    elif style == "教程讲解":
        lines = [
            f"这条视频用最短时间讲清楚：{title}。",
            f"先看场景，{key}通常卡在信息太散、步骤太乱、结果不可复用。",
            f"做法很简单，先定目标，再拆步骤，最后把输出变成可检查的结果。",
            f"如果中间出现偏差，就回到{second}这个关键点重新校准。",
            "照这个顺序走，观众不用猜，也知道下一步该怎么做。",
        ]
    elif style == "产品发布":
        lines = [
            f"{title}，解决的是一个很具体的问题。",
            f"过去做{key}，往往要来回复制、等待、整理，还很难稳定复用。",
            f"现在把流程封装起来，一次输入，就能连续完成文案、素材和结果输出。",
            f"它的价值不在炫技，而在减少重复劳动，让好流程可以被分享和安装。",
            "如果你也有固定流程，把它做成卡带，就能从工具变成可分发的产品。",
        ]
    else:
        lines = [
            f"今天讲清楚一个问题：{title}。",
            f"很多人只看到{key}的表面，却忽略了背后的真实原因。",
            f"把它拆开看，核心其实是场景、动作和结果之间有没有形成闭环。",
            f"一旦抓住{second}这个关键点，复杂问题就能变成几个可执行步骤。",
            "最后记住一句话：好的内容不是堆信息，而是让观众立刻知道该怎么行动。",
        ]
    return lines[:scene_count]

def _scene_onscreen_texts(title: str, topic: str, keywords: list[str], scene_count: int) -> list[str]:
    key = keywords[0] if keywords else title[:8]
    second = keywords[1] if len(keywords) > 1 else "关键转折"
    texts = [
        title,
        f"{key}为什么重要",
        f"{second}是转折",
        "下一步怎么做",
        "记住这句话",
    ]
    return texts[:scene_count]

def _scene_visual_prompt(style: str, topic: str, keyword_a: str, keyword_b: str, index: int) -> str:
    moods = ["强钩子开场", "问题放大", "关键转折", "行动方案", "收束结论"]
    return (
        f"{style}，竖屏短视频分镜，{moods[index % len(moods)]}。"
        f"主题：{topic}。关键词：{keyword_a}、{keyword_b}。"
        "电影感但信息清晰，主体明确，高对比光影，适合手机观看；不要水印，不要品牌标识，不要画面文字。"
    )

def _maybe_generate_scene_images(target_dir: Path, stem: str, project: dict, provider: str) -> list[Path]:
    if provider in {"off", "local", "none"}:
        project["integrations"]["image"] = {"provider": "local", "status": "skipped", "outputs": []}
        return []
    providers = _image_provider_order(provider)
    if not providers:
        project["integrations"]["image"] = {"provider": "local", "status": "missing_api_key", "outputs": []}
        return []
    outputs = []
    errors = []
    for scene in project.get("scenes", []):
        prompt = (
            f"{scene.get('visual_prompt')}\n"
            f"画面文字：{scene.get('onscreen_text')}\n"
            "不要使用真实品牌标识，不要出现水印。"
        )
        image_bytes = None
        used_provider = ""
        for provider_name in providers:
            try:
                image_bytes = _image_bytes(provider_name, prompt)
                used_provider = provider_name
                break
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
        if image_bytes:
            image_path = target_dir / f"{stem}.scene_{int(scene.get('index', 0)):02d}.png"
            image_path.write_bytes(image_bytes)
            scene["image_path"] = image_path.name
            scene["_image_path_abs"] = str(image_path)
            scene["image_provider"] = used_provider
            outputs.append(image_path)
    project["integrations"]["image"] = {
        "provider": provider if provider not in {"auto", ""} else "auto",
        "resolved_provider": _dominant_image_provider(project),
        "status": "ok" if outputs else "fallback",
        "outputs": [item.name for item in outputs],
        "errors": errors[:6],
    }
    return outputs

def _image_provider_order(provider: str) -> list[str]:
    requested = (provider or "auto").strip().lower()
    aliases = {
        "openai": "openai",
        "gpt-image": "openai",
        "gpt_image": "openai",
        "stability": "stability",
        "stable-diffusion": "stability",
        "sd": "stability",
        "huggingface": "huggingface",
        "hf": "huggingface",
    }
    if requested == "auto":
        order = []
        if os.environ.get("OPENAI_API_KEY", "").strip():
            order.append("openai")
        if os.environ.get("STABILITY_API_KEY", "").strip():
            order.append("stability")
        if os.environ.get("HF_TOKEN", "").strip() or os.environ.get("HUGGINGFACE_API_KEY", "").strip():
            order.append("huggingface")
        return order
    mapped = aliases.get(requested, requested)
    return [mapped] if mapped in {"openai", "stability", "huggingface"} else []

def _image_bytes(provider: str, prompt: str) -> bytes:
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("missing OPENAI_API_KEY")
        model = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1").strip()
        size = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024").strip()
        return _openai_image_bytes(api_key, model, prompt, size)
    if provider == "stability":
        api_key = os.environ.get("STABILITY_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("missing STABILITY_API_KEY")
        model = os.environ.get("STABILITY_IMAGE_MODEL", "stable-image-core").strip()
        return _stability_image_bytes(api_key, model, prompt)
    if provider == "huggingface":
        api_key = os.environ.get("HF_TOKEN", "").strip() or os.environ.get("HUGGINGFACE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("missing HF_TOKEN")
        model = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()
        return _huggingface_image_bytes(api_key, model, prompt)
    raise RuntimeError(f"unsupported image provider: {provider}")

def _dominant_image_provider(project: dict) -> str:
    providers = [
        str(scene.get("image_provider") or "")
        for scene in project.get("scenes", [])
        if scene.get("image_provider")
    ]
    if not providers:
        return "local"
    return max(set(providers), key=providers.count)

def _openai_image_bytes(api_key: str, model: str, prompt: str, size: str) -> bytes:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }).encode("utf-8")
    data = _openai_post_json("https://api.openai.com/v1/images/generations", api_key, payload)
    first = (data.get("data") or [{}])[0]
    if first.get("b64_json"):
        return base64.b64decode(first["b64_json"])
    if first.get("url"):
        request = urllib.request.Request(first["url"], headers={"User-Agent": "CartridgeFlow/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    raise RuntimeError("OpenAI image response did not include b64_json or url")

def _stability_image_bytes(api_key: str, model: str, prompt: str) -> bytes:
    if model in {"stable-image-core", "core"}:
        url = "https://api.stability.ai/v2beta/stable-image/generate/core"
        fields = {
            "prompt": prompt,
            "aspect_ratio": os.environ.get("STABILITY_ASPECT_RATIO", "9:16").strip() or "9:16",
            "output_format": os.environ.get("STABILITY_OUTPUT_FORMAT", "png").strip() or "png",
        }
    else:
        url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
        fields = {
            "prompt": prompt,
            "model": model,
            "aspect_ratio": os.environ.get("STABILITY_ASPECT_RATIO", "9:16").strip() or "9:16",
            "output_format": os.environ.get("STABILITY_OUTPUT_FORMAT", "png").strip() or "png",
        }
    body, content_type = _multipart_form_data(fields)
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/*",
            "Content-Type": content_type,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Stability API HTTP {exc.code}: {body[:500]}") from exc

def _huggingface_image_bytes(api_key: str, model: str, prompt: str) -> bytes:
    endpoint = os.environ.get("HF_IMAGE_ENDPOINT", "").strip()
    url = endpoint or f"https://api-inference.huggingface.co/models/{model}"
    payload = json.dumps({
        "inputs": prompt,
        "parameters": {
            "height": _safe_int(os.environ.get("HF_IMAGE_HEIGHT"), 1024, 256, 1536),
            "width": _safe_int(os.environ.get("HF_IMAGE_WIDTH"), 576, 256, 1536),
        },
        "options": {"wait_for_model": True},
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/png",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
            if "application/json" in content_type:
                raise RuntimeError(data.decode("utf-8", errors="replace")[:500])
            return data
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Hugging Face API HTTP {exc.code}: {body[:500]}") from exc

def _multipart_form_data(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----CartridgeFlow{hashlib.sha256(json.dumps(fields, sort_keys=True).encode('utf-8')).hexdigest()[:16]}"
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

def _maybe_generate_openai_voiceover(audio_path: Path, project: dict, provider: str) -> Path | None:
    if provider in {"off", "local", "none"}:
        project["integrations"]["tts"] = {"provider": "local", "status": "skipped", "output": ""}
        return None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        project["integrations"]["tts"] = {"provider": "local", "status": "missing_api_key", "output": ""}
        return None
    model = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip()
    voice = os.environ.get("OPENAI_TTS_VOICE", "alloy").strip()
    text = "\n".join(_clean_spoken_text(scene.get("narration") or scene.get("voiceover") or "") for scene in project.get("scenes", []))
    try:
        payload = json.dumps({
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "wav",
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            audio_path.write_bytes(response.read())
        project["integrations"]["tts"] = {"provider": "openai", "model": model, "voice": voice, "status": "ok", "output": audio_path.name}
        return audio_path
    except Exception as exc:
        project["integrations"]["tts"] = {"provider": "openai", "model": model, "voice": voice, "status": "fallback", "error": str(exc)}
        return None

def _openai_post_json(url: str, api_key: str, payload: bytes) -> dict:
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {body[:500]}") from exc

def _maybe_compose_mp4(mp4_path: Path, avi_path: Path, audio_path: Path, provider: str) -> Path | None:
    if provider in {"off", "local", "none"}:
        return None
    ffmpeg = _find_ffmpeg_binary(avi_path)
    if not ffmpeg:
        return None
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(avi_path),
        "-i",
        str(audio_path),
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(mp4_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    except Exception:
        return None
    return mp4_path if mp4_path.exists() else None

def _write_voiceover_wav(path: Path, project: dict) -> dict:
    voiceover_text = "\n".join(_clean_spoken_text(scene.get("narration") or scene.get("voiceover") or "") for scene in project.get("scenes", []))
    system_tts = _write_system_tts_wav(path, voiceover_text)
    if system_tts:
        return {"provider": "system_tts", "status": "ok", "output": path.name}
    _write_tone_voiceover_wav(path, project)
    return {"provider": "local_tone", "status": "fallback", "output": path.name}

def _write_system_tts_wav(path: Path, text: str) -> bool:
    if os.name != "nt" or not text.strip():
        return False
    text_path = path.with_name(f"{path.stem}.tts.txt")
    text_path.write_text(_clean_spoken_text(text), encoding="utf-8")
    safe_path = str(path).replace("'", "''")
    safe_text_path = str(text_path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        f"$text = Get-Content -LiteralPath '{safe_text_path}' -Raw -Encoding UTF8; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = 1; $s.Volume = 100; "
        f"$s.SetOutputToWaveFile('{safe_path}'); "
        "$s.Speak($text); "
        "$s.Dispose();"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=90,
        )
    except Exception:
        try:
            text_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    try:
        text_path.unlink(missing_ok=True)
    except Exception:
        pass
    return path.exists() and path.stat().st_size > 1024

def _write_tone_voiceover_wav(path: Path, project: dict):
    sample_rate = 16000
    duration = int(project.get("duration_seconds") or 15)
    text = "|".join(_clean_spoken_text(scene.get("narration") or scene.get("voiceover") or "") for scene in project.get("scenes", []))
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
    samples = bytearray()
    for i in range(sample_rate * duration):
        t = i / sample_rate
        scene_index = min(len(project["scenes"]) - 1, int(t / max(1, duration / len(project["scenes"]))))
        scene_text = project["scenes"][scene_index].get("narration") or project["scenes"][scene_index].get("voiceover") or ""
        scene_seed = int(hashlib.sha256(scene_text.encode("utf-8")).hexdigest()[:6], 16)
        syllable_rate = 3.0 + (scene_seed % 7) * 0.35
        freq = 210 + (seed % 120) + scene_index * 38 + ((scene_seed >> 4) % 80)
        envelope = 0.18 + 0.82 * (0.5 + 0.5 * math.sin(2 * math.pi * syllable_rate * t))
        carrier = math.sin(2 * math.pi * freq * t) + 0.35 * math.sin(2 * math.pi * (freq * 1.5) * t)
        value = int(7600 * envelope * carrier)
        samples.extend(struct.pack("<h", value))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(samples))

def _write_avi(path: Path, project: dict):
    width = int(project["format"]["width"])
    height = int(project["format"]["height"])
    fps = int(project["format"]["fps"])
    duration = int(project["duration_seconds"])
    frame_count = fps * duration
    frames = [_render_frame(width, height, project, frame_index / fps) for frame_index in range(frame_count)]
    _write_avi_frames(path, width, height, fps, frames)

def _write_avi_frames(path: Path, width: int, height: int, fps: int, frames: list[bytes]):
    frame_count = len(frames)
    if not frames:
        raise ValueError("AVI 至少需要一帧")
    frame_size = len(frames[0])
    movi_payload = bytearray()
    index_entries = []
    for frame in frames:
        offset = len(movi_payload) + 4
        movi_payload += b"00db" + struct.pack("<I", len(frame)) + frame
        if len(frame) % 2:
            movi_payload += b"\0"
        index_entries.append((b"00db", 0x10, offset, len(frame)))

    hdrl = _list_chunk(b"hdrl", _avih(frame_count, fps, frame_size, width, height) + _video_stream_header(frame_count, fps, frame_size, width, height))
    movi = _list_chunk(b"movi", bytes(movi_payload))
    idx1 = b"idx1" + struct.pack("<I", len(index_entries) * 16) + b"".join(
        chunk_id + struct.pack("<III", flags, offset, size)
        for chunk_id, flags, offset, size in index_entries
    )
    riff_payload = hdrl + movi + idx1
    path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_payload) + 4) + b"AVI " + riff_payload)

def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    return chunk_id + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")

def _list_chunk(list_type: bytes, payload: bytes) -> bytes:
    return b"LIST" + struct.pack("<I", len(payload) + 4) + list_type + payload + (b"\0" if len(payload) % 2 else b"")

def _avih(frame_count: int, fps: int, frame_size: int, width: int, height: int) -> bytes:
    payload = struct.pack(
        "<IIIIIIIIIIIIII",
        int(1_000_000 / fps),
        frame_size * fps,
        0,
        0x10,
        frame_count,
        0,
        1,
        frame_size,
        width,
        height,
        0,
        0,
        0,
        0,
    )
    return _chunk(b"avih", payload)

def _video_stream_header(frame_count: int, fps: int, frame_size: int, width: int, height: int) -> bytes:
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"DIB ",
        0,
        0,
        0,
        0,
        1,
        fps,
        0,
        frame_count,
        frame_size,
        0xFFFFFFFF,
        0,
        0,
        0,
        width,
        height,
    )
    strf = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        24,
        0,
        frame_size,
        0,
        0,
        0,
        0,
    )
    return _list_chunk(b"strl", _chunk(b"strh", strh) + _chunk(b"strf", strf))

def _render_frame(width: int, height: int, project: dict, second: float) -> bytes:
    scenes = project["scenes"]
    scene = scenes[-1]
    for item in scenes:
        if item["start"] <= second < item["end"]:
            scene = item
            break
    try:
        return _render_pillow_frame(width, height, project, scene, second)
    except Exception:
        return _render_basic_frame(width, height, project, scene, second)

def _render_pillow_frame(width: int, height: int, project: dict, scene: dict, second: float) -> bytes:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

    bg = _hex_to_rgb(scene["palette"]["background"])
    accent = _hex_to_rgb(scene["palette"]["accent"])
    soft = _hex_to_rgb(scene["palette"]["soft"])
    seed = int(project.get("seed") or 0) + int(scene.get("index") or 0) * 7919
    image_path = _scene_image_path(project, scene)
    if image_path and image_path.exists():
        source = Image.open(image_path).convert("RGB")
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        img = ImageOps.fit(source, (width, height), method=resampling)
        img = img.filter(ImageFilter.GaussianBlur(0.7))
    else:
        img = Image.new("RGB", (width, height), bg)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(height):
        amount = y / max(1, height - 1)
        color = _mix(bg, soft, 0.08 + 0.18 * amount)
        alpha = 170 if image_path else 255
        draw.line([(0, y), (width, y)], fill=(*color, alpha))

    if image_path:
        draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 88))
    else:
        for i in range(9):
            cx = (seed * (i + 3) * 37 + i * 73) % (width + 160) - 80
            cy = (seed * (i + 5) * 19 + i * 97) % (height + 160) - 80
            radius = 34 + ((seed >> (i % 12)) % 70)
            color = accent if i % 2 == 0 else soft
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*color, 42))

    card_top = 88 + int(8 * math.sin(second * 1.6 + scene.get("index", 1)))
    draw.rounded_rectangle((24, card_top, width - 24, height - 92), radius=24, fill=(15, 23, 42, 210), outline=(*accent, 210), width=2)
    draw.rounded_rectangle((38, card_top + 20, width - 38, card_top + 76), radius=18, fill=(*accent, 235))

    title_font = _font(22, bold=True)
    hero_font = _font(36, bold=True)
    body_font = _font(19)
    small_font = _font(15)
    draw.text((50, card_top + 32), f"#{scene.get('index')}  {project.get('style')}", font=small_font, fill=(255, 255, 255, 245))

    title_lines = _wrap_text(str(project.get("title") or ""), title_font, width - 72, max_lines=2)
    y = 36
    for line in title_lines:
        _draw_text_shadow(draw, (28, y), line, title_font, (255, 255, 255, 255))
        y += 28

    hero = str(scene.get("onscreen_text") or scene.get("title") or "")
    hero_lines = _wrap_text(hero, hero_font, width - 92, max_lines=3)
    y = card_top + 112
    for line in hero_lines:
        bbox = draw.textbbox((0, 0), line, font=hero_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        _draw_text_shadow(draw, (x, y), line, hero_font, (255, 255, 255, 255), shadow=(0, 0, 0, 170))
        y += 46

    subtitle = str(scene.get("subtitle") or scene.get("voiceover") or "")
    subtitle_lines = _wrap_text(subtitle, body_font, width - 80, max_lines=3)
    subtitle_top = height - 206
    draw.rounded_rectangle((34, subtitle_top - 12, width - 34, subtitle_top + 92), radius=18, fill=(0, 0, 0, 130))
    y = subtitle_top
    for line in subtitle_lines:
        _draw_text_shadow(draw, (48, y), line, body_font, (255, 255, 255, 245))
        y += 28

    total = max(1, int(project.get("duration_seconds") or 1))
    progress = max(0.0, min(1.0, second / total))
    draw.rounded_rectangle((34, height - 58, width - 34, height - 48), radius=5, fill=(255, 255, 255, 70))
    draw.rounded_rectangle((34, height - 58, 34 + int((width - 68) * progress), height - 48), radius=5, fill=(*accent, 255))
    draw.text((34, height - 38), f"{int(second):02d}s / {total:02d}s", font=small_font, fill=(255, 255, 255, 210))

    overlay = overlay.filter(ImageFilter.GaussianBlur(0.15))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _image_to_avi_frame(img)

def _scene_image_path(project: dict, scene: dict) -> Path | None:
    raw = scene.get("_image_path_abs")
    if raw:
        return Path(str(raw))
    image_name = scene.get("image_path")
    target_dir = project.get("_target_dir")
    if image_name and target_dir:
        return Path(str(target_dir)) / str(image_name)
    return None

def _render_basic_frame(width: int, height: int, project: dict, scene: dict, second: float) -> bytes:
    bg = _hex_to_rgb(scene["palette"]["background"])
    accent = _hex_to_rgb(scene["palette"]["accent"])
    soft = _hex_to_rgb(scene["palette"]["soft"])
    progress = (second - scene["start"]) / max(1, scene["end"] - scene["start"])
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            stripe = int(36 * math.sin((x + second * 18) / 28) + 28 * math.cos((y - second * 11) / 36))
            in_panel = 54 < x < width - 54 and 160 < y < height - 150
            in_bar = y > height - 42 and x < int(width * progress)
            in_badge = (x - width // 2) ** 2 + (y - height // 2) ** 2 < (48 + 10 * math.sin(second * 2)) ** 2
            color = bg
            if stripe > 28:
                color = _mix(bg, accent, 0.22)
            if in_panel:
                color = _mix(color, soft, 0.62)
            if in_badge or in_bar:
                color = accent
            row.extend(bytes((color[2], color[1], color[0])))
        while len(row) % 4:
            row.append(0)
        rows.append(bytes(row))
    return b"".join(rows)

def _image_to_avi_frame(img) -> bytes:
    width, height = img.size
    raw = img.tobytes("raw", "BGR")
    stride = width * 3
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray(raw[y * stride:(y + 1) * stride])
        while len(row) % 4:
            row.append(0)
        rows.append(bytes(row))
    return b"".join(rows)

def _write_png_from_bgr_frame(path: Path, width: int, height: int, frame: bytes) -> None:
    stride = width * 3
    padded_stride = stride
    while padded_stride % 4:
        padded_stride += 1
    scanlines = bytearray()
    for y in range(height):
        source_y = height - 1 - y
        row = frame[source_y * padded_stride:source_y * padded_stride + stride]
        scanlines.append(0)
        for x in range(0, len(row), 3):
            b, g, r = row[x:x + 3]
            scanlines.extend((r, g, b))
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + chunk_type
            + payload
            + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(scanlines), 6))
        + chunk(b"IEND", b"")
    )

def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        try:
            if path and Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()

def _wrap_text(text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text = " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())
    if not text:
        return []
    lines = []
    current = ""
    for ch in text:
        candidate = current + ch
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = ch
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len("".join(lines)) < len(text):
        lines[-1] = lines[-1].rstrip("，。,. ") + "..."
    return lines

def _draw_text_shadow(draw, pos, text: str, font, fill, shadow=(0, 0, 0, 135)):
    x, y = pos
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)

def _public_project(project: dict) -> dict:
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if not str(k).startswith("_")}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(project)

def _render_preview_html(project: dict, video_name: str, audio_name: str) -> str:
    audio_muxed = bool((project.get("integrations", {}).get("video") or {}).get("audio_muxed"))
    status = "当前视频文件已封装音频。" if audio_muxed else "当前环境未检测到 FFmpeg，视频与音轨分开输出；下面预览会同时播放两者。"
    scene_html = "\n".join(
        f"<li><b>{item['start']:02d}s-{item['end']:02d}s</b> {html.escape(item['onscreen_text'])}<p>{html.escape(item.get('narration') or item.get('voiceover') or '')}</p></li>"
        for item in project["scenes"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8" />
<title>{html.escape(project['title'])}</title>
<style>
body{{margin:0;background:#111827;color:#f9fafb;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
main{{max-width:920px;margin:0 auto;padding:28px;display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:24px;}}
video,audio{{width:100%;}}
video{{aspect-ratio:9/16;background:#000;border-radius:8px;}}
section{{background:#1f2937;border:1px solid #374151;border-radius:8px;padding:18px;}}
h1{{font-size:26px;margin:0 0 8px;}} p{{color:#d1d5db;line-height:1.7;}} li{{margin:0 0 14px;}} a{{color:#fbbf24;}}
.media{{display:grid;gap:12px;align-content:start;}}
.status{{color:#fbbf24;}}
</style>
<main>
  <div class="media">
    <video id="video" src="{html.escape(video_name)}" controls loop></video>
    <audio id="audio" src="{html.escape(audio_name)}" controls></audio>
  </div>
  <section>
    <h1>{html.escape(project['title'])}</h1>
    <p>{html.escape(project['notes'])}</p>
    <p class="status">{html.escape(status)}</p>
    <p><a href="{html.escape(video_name)}">下载视频文件</a> · <a href="{html.escape(audio_name)}">下载 WAV 音轨</a></p>
    <ol>{scene_html}</ol>
  </section>
</main>
<script>
const video = document.getElementById('video');
const audio = document.getElementById('audio');
if (video && audio) {{
  video.addEventListener('play', () => {{ audio.currentTime = video.currentTime; audio.play().catch(() => {{}}); }});
  video.addEventListener('pause', () => audio.pause());
  video.addEventListener('seeked', () => {{ audio.currentTime = video.currentTime; }});
  video.addEventListener('ended', () => {{ audio.pause(); audio.currentTime = 0; }});
}}
</script>
</html>
"""


def register(registry):
    def generate_short_video(params: dict) -> dict:
        idea = str(params.get("idea") or params.get("brief") or params.get("topic") or params.get("title") or "").strip()
        if not idea:
            return {"ok": False, "error": "缺少 idea：请至少输入一个短视频想法"}
        title = str(params.get("title") or "").strip()
        topic = str(params.get("topic") or "").strip()
        style = str(params.get("style") or "自动匹配").strip()
        audience = str(params.get("audience") or "").strip()
        plan_text = str(params.get("plan") or params.get("video_plan") or "").strip()
        duration = _safe_int(params.get("duration_seconds"), 15, 6, 60)
        output_dir = str(params.get("output_dir") or "test_output/short_video").strip()
        image_provider = str(params.get("image_provider") or "auto").strip().lower()
        voice_provider = str(params.get("voice_provider") or "auto").strip().lower()
        compose_provider = str(params.get("compose_provider") or "auto").strip().lower()
        try:
            target_dir = registry._safe_path(output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            project = _build_short_video_project(idea, title, topic, style, audience, duration, plan_text)
            project["_target_dir"] = str(target_dir)
            stem = _safe_slug(str(params.get("filename_prefix") or project["title"] or idea or "short_video"))
            avi_path = target_dir / f"{stem}.avi"
            audio_path = target_dir / f"{stem}.wav"
            project_path = target_dir / f"{stem}.project.json"
            html_path = target_dir / f"{stem}.preview.html"
            image_paths = _maybe_generate_scene_images(target_dir, stem, project, image_provider)
            tts_path = _maybe_generate_openai_voiceover(audio_path, project, voice_provider)
            if not tts_path:
                project["integrations"]["tts"] = _write_voiceover_wav(audio_path, project)
            _write_avi(avi_path, project)
            video_path = _maybe_compose_mp4(target_dir / f"{stem}.mp4", avi_path, audio_path, compose_provider) or avi_path
            project["integrations"]["video"] = {
                "provider": "ffmpeg" if video_path.suffix.lower() == ".mp4" else "local_avi",
                "status": "ok" if video_path.exists() else "fallback",
                "output": video_path.name,
                "source_avi": avi_path.name,
                "audio_muxed": video_path.suffix.lower() == ".mp4",
            }
            public_project = _public_project(project)
            project_path.write_text(json.dumps(public_project, ensure_ascii=False, indent=2), encoding="utf-8")
            html_path.write_text(_render_preview_html(project, video_path.name, audio_path.name), encoding="utf-8")
            rel_files = []
            for item in [video_path, audio_path, project_path, html_path, *image_paths, avi_path]:
                if item in {video_path} or item.exists():
                    rel_files.append(str(item.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"))
            rel_files = list(dict.fromkeys(rel_files))
            primary = {
                "video": str(video_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
                "audio": str(audio_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
                "project": str(project_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
                "preview": str(html_path.resolve().relative_to(registry._workspace_root.resolve())).replace("\\", "/"),
            }
            return {
                "ok": True,
                "path": str(video_path),
                "video_path": str(video_path),
                "audio_path": str(audio_path),
                "project_path": str(project_path),
                "preview_path": str(html_path),
                "files": rel_files,
                "content": json.dumps({
                    "title": project["title"],
                    "duration_seconds": duration,
                    **primary,
                    "scenes": len(project["scenes"]),
                    "integrations": project.get("integrations", {}),
                }, ensure_ascii=False, indent=2),
            }
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": f"短视频生成失败：{exc}"}

    registry._registry["media"].update({
        'generate_short_video': generate_short_video,
    })
