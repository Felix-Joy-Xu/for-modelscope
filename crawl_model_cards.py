#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代表性模型卡片全文采集
=====================
20 个代表性模型的 README/Model Card 全文
反映: 许可证叙述、使用限制声明、国产叙事、国际合作说明
"""
import os, json, time, requests

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "modelscope_output")
CARDS_DIR = os.path.join(OUTPUT_DIR, "model_cards")
os.makedirs(CARDS_DIR, exist_ok=True)

# 20 个代表性样本（覆盖国产/国际/多模态/端到端/对话/embedding 等）
SAMPLES = [
    # 国产大语言模型
    ("qwen/Qwen2.5-7B-Instruct", "通义千问2.5（国产LLM标准品）"),
    ("qwen/Qwen2.5-72B-Instruct", "通义千问2.5-72B（旗舰LLM）"),
    ("Qwen/Qwen3-235B-A22B", "通义千问3旗舰MoE"),
    ("deepseek-ai/DeepSeek-V3", "DeepSeek-V3（中国现象级开源）"),
    ("deepseek-ai/DeepSeek-R1", "DeepSeek-R1（推理模型）"),
    ("ZhipuAI/glm-4-9b", "智谱GLM-4（清华系）"),
    ("ZhipuAI/glm-4-9b-chat", "智谱GLM-4对话版"),
    ("baichuan-inc/Baichuan2-13B-Chat", "百川2-13B（百川智能）"),
    ("01ai/Yi-1.5-34B-Chat", "零一万物Yi-1.5-34B"),
    ("internlm/internlm2_5-7b-chat", "上海AI Lab InternLM2.5"),
    # 国际开源（镜像到魔搭）
    ("LLM-Research/Meta-Llama-3-8B-Instruct", "Llama-3-8B（Meta-镜像到魔搭）"),
    ("LLM-Research/Mistral-7B-Instruct-v0.2", "Mistral-7B（镜像）"),
    ("AI-ModelScope/gemma-2-2b-it", "Google Gemma-2-2B（镜像）"),
    ("mlx-community/Phi-3.5-mini-instruct-8bit", "微软Phi-3.5（镜像）"),
    # 多模态
    ("qwen/Qwen2-VL-7B-Instruct", "Qwen2-VL视觉语言模型"),
    ("AI-ModelScope/InternVL-Chat-V1-5", "InternVL多模态"),
    # 中文特色
    ("iic/nlp_structbert_word-segmentation_chinese-base", "达摩院中文分词（魔搭最早模型之一）"),
    ("damo/nlp_gpt3_text-generation_1.3B", "达摩院GPT3-1.3B中文"),
    # 国产新兴
    ("XiaomiMiMo/XiaomiMiMo-VL-7B-RL-2508", "小米MiMo-VL-7B"),
    ("AI-ModelScope/Hunyuan-7B-Instruct", "腾讯混元7B Instruct"),
]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

all_cards = []
for model_id, label in SAMPLES:
    safe_name = model_id.replace("/", "_")
    urls = [
        f"https://www.modelscope.cn/models/{model_id}/resolve/master/README.md",
        f"https://www.modelscope.cn/api/v1/models/{model_id}/repo?Revision=master&FilePath=README.md",
    ]

    content = None
    used_url = None
    for url in urls:
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200 and len(r.text) > 50:
                content = r.text
                used_url = url
                break
        except:
            continue
        time.sleep(0.3)

    if content:
        # 保存为单独文件
        with open(os.path.join(CARDS_DIR, f"{safe_name}_README.md"), "w", encoding="utf-8") as f:
            f.write(content)

        card = {
            "model_id": model_id,
            "label": label,
            "readme_length": len(content),
            "url_used": used_url[:80],
            "readme_preview": content[:500],
            "has_license_section": "license" in content.lower(),
            "has_disclaimer": any(k in content.lower() for k in ["disclaimer", "免责", "声明", "使用限制"]),
            "has_chinese_narrative": any(k in content for k in ["国产", "自主", "中国", "开源", "通义", "达摩"]),
            "has_training_data": "training data" in content.lower() or "训练数据" in content,
        }
        all_cards.append(card)
        print(f"  [OK] {model_id:48s} {len(content):>6} chars | {label[:25]}")
    else:
        print(f"  [FAIL] {model_id:48s} | {label}")

    time.sleep(0.3)

# 保存汇总
with open(os.path.join(OUTPUT_DIR, "model_cards_index.json"), "w", encoding="utf-8") as f:
    json.dump(all_cards, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"完成: {len(all_cards)}/{len(SAMPLES)} 个模型卡片全文")
print(f"  存Individual README: {CARDS_DIR}/")
print(f"  索引文件: model_cards_index.json")
print(f"{'='*60}")
# 关键指标汇总
with_license = sum(1 for c in all_cards if c["has_license_section"])
with_disclaimer = sum(1 for c in all_cards if c["has_disclaimer"])
with_narrative = sum(1 for c in all_cards if c["has_chinese_narrative"])
with_training = sum(1 for c in all_cards if c["has_training_data"])
print(f"  含 license 章: {with_license}/{len(all_cards)}")
print(f"  含免责/使用限制章: {with_disclaimer}/{len(all_cards)}")
print(f"  含国产/自主/开源语词: {with_narrative}/{len(all_cards)}")
print(f"  含训练数据说明: {with_training}/{len(all_cards)}")