"""汇总模型卡片采集"""
import os, json
d = "D:/国际比较政治经济学/01-爬虫程序/modelscope_output"
cards_dir = os.path.join(d, "model_cards")
cards = sorted([f for f in os.listdir(cards_dir) if f.endswith(".md")])

print(f"卡片数: {len(cards)}")
total = 0
for c in cards:
    with open(os.path.join(cards_dir, c), "r", encoding="utf-8") as f:
        chars = len(f.read())
    total += chars
    print(f"  {c:55s} {chars:>6,} chars")
print(f"\n总计: {total:,} chars")

with open(os.path.join(d, "model_cards_index.json"), "r", encoding="utf-8") as f:
    idx = json.load(f)

lic = sum(1 for i in idx if i["has_license_section"])
dis = sum(1 for i in idx if i["has_disclaimer"])
nar = sum(1 for i in idx if i["has_chinese_narrative"])
td = sum(1 for i in idx if i["has_training_data"])
print()
print(f"含 license 章:    {lic}/{len(idx)}")
print(f"含使用限制/免责:   {dis}/{len(idx)}")
print(f"含国产/自主/开源:  {nar}/{len(idx)}")
print(f"含训练数据说明:    {td}/{len(idx)}")