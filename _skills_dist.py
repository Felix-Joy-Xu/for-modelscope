"""BOSS 数据库 — 技能分布深度分析"""
import sqlite3
from collections import Counter

DB = r'D:\hiring_data\boss_api\boss_jobs.db'

print("=" * 70)
print("=== BOSS 直聘 — 技能分布分析 ===")
print("=" * 70)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# ── 加载所有 skills 数据 ──
cur.execute("SELECT skills, salary_avg_k, city FROM jobs WHERE skills IS NOT NULL AND skills != ''")
rows = cur.fetchall()
print(f"\n有技能标签的样本: {len(rows):,} / 72,026 ({len(rows)/72026*100:.1f}%)\n")

# ── 解析技能 ──
skill_counter = Counter()
skill_city = {}  # skill -> Counter of cities
skill_salaries = {}  # skill -> list of salaries
city_counter = Counter()

for skills_str, salary, city in rows:
    if not skills_str:
        continue
    skills = [s.strip() for s in skills_str.split('|') if s.strip()]
    for sk in skills:
        skill_counter[sk] += 1
        if city:
            if sk not in skill_city:
                skill_city[sk] = Counter()
            skill_city[sk][city] += 1
        if salary:
            sal = float(salary)
            if sal > 0:
                if sk not in skill_salaries:
                    skill_salaries[sk] = []
                skill_salaries[sk].append(sal)

# ── 去除非技能标签 ──
NON_SKILL_FLAGS = {
    '不接受居家办公', '接受居家办公', '居家办公', '远程办公',
    '现场办公', '线下办公',
}
SKIP_PATTERNS = [
    '经验', '相关专业', '专业', '开发经验', '设计经验',
    '办公', '保险', '财险', '车险',
]
def is_real_skill(sk):
    if sk in NON_SKILL_FLAGS:
        return False
    for pat in SKIP_PATTERNS:
        if pat in sk:
            return False
    # Also skip pure chinese phrases that are too generic
    generic = {'后端', '前端', '全栈', '测试', '算法', '数据', '运维', '产品', '设计', '运营'}
    if sk in generic:
        return False
    return True

real_skills = {
    sk: cnt for sk, cnt in skill_counter.most_common()
    if is_real_skill(sk)
}

top_skills = list(real_skills.items())[:60]

# ═══════════════════════════════════════════
# 1. 顶级技能频率 (Top 60)
# ═══════════════════════════════════════════
print("─" * 60)
print("【1. 技能需求 Top 60】")
print(f"  {'技能':<30s} {'出现次数':>6s}  {'占比':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*8}")
for sk, cnt in top_skills:
    pct = cnt / len(rows) * 100
    sals = skill_salaries.get(sk, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    bar = '█' * max(1, int(cnt / top_skills[0][1] * 40))
    print(f"  {sk[:30]:30s} {cnt:>6,}  {pct:>5.1f}%  {avg_sal:>7.1f}k {bar}")

# ═══════════════════════════════════════════
# 2. 语言排行
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【2. 编程语言排行】")
LANGUAGES = [
    'Java', 'Python', 'JavaScript', 'TypeScript', 'C++', 'C', 'C#', 'Golang', 'Go',
    'PHP', 'Rust', 'Ruby', 'Scala', 'Kotlin', 'Swift', 'MATLAB', 'R', 'Shell', 'SQL',
    'Node.js', 'HTML', 'HTML5', 'CSS', 'CSS3',
]
lang_stats = []
for lang in LANGUAGES:
    cnt = skill_counter.get(lang, 0)
    if cnt == 0:
        continue
    sals = skill_salaries.get(lang, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    lang_stats.append((lang, cnt, avg_sal))
lang_stats.sort(key=lambda x: -x[1])
print(f"  {'语言':<15s} {'出现次数':>6s}  {'占比':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*15} {'-'*6} {'-'*6} {'-'*8}")
for lang, cnt, avg_sal in lang_stats[:20]:
    pct = cnt / len(rows) * 100
    print(f"  {lang:<15s} {cnt:>6,}  {pct:>5.1f}%  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 3. 框架/库排行
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【3. 框架与库 Top 30】")
FRAMEWORKS = [
    'Spring', 'SpringCloud', 'SpringBoot', 'MyBatis', 'Hibernate', 'Dubbo',
    'Django', 'Flask', 'FastAPI', 'Tornado', 'Express', 'Koa', 'NestJS',
    'React', 'Vue', 'Vue.js', 'Angular', 'jQuery', 'Bootstrap',
    'Netty', 'Kafka', 'RabbitMQ', 'RocketMQ', 'Elasticsearch', 'Nginx',
    'Docker', 'Kubernetes', 'K8s', 'Jenkins', 'Git', 'Linux',
    'Hadoop', 'Spark', 'Flink', 'Hive', 'HBase', 'Storm',
    'Pandas', 'NumPy', 'Scikit-learn', 'scikit-learn', 'TensorFlow', 'PyTorch',
    'LangChain', 'LlamaIndex',
    'Redis', 'MySQL', 'PostgreSQL', 'MongoDB', 'Oracle', 'SQL Server', 'ElasticSearch',
    'gRPC', 'GraphQL', 'REST', 'WebSocket',
    'JVM', 'GC', 'CI/CD', 'DevOps', 'Maven', 'Gradle',
    'Unity', 'Unreal', 'Cocos',
    'Laravel', 'ThinkPHP', 'Yii', 'Symfony',
    'ZooKeeper', 'Nacos', 'Consul', 'Etcd',
    'MyCat', 'ShardingSphere',
    'GitLab', 'GitHub',
    'PySpark', 'Airflow', 'Hive',  
]
fw_stats = []
seen = set()
for fw in FRAMEWORKS:
    cnt = skill_counter.get(fw, 0)
    if cnt == 0:
        continue
    seen.add(fw)
    sals = skill_salaries.get(fw, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    fw_stats.append((fw, cnt, avg_sal))

# Also pull top by count not in our predefined list
for sk, cnt in real_skills.items():
    if sk not in seen and cnt >= 500:
        seen.add(sk)
        sals = skill_salaries.get(sk, [])
        avg_sal = sum(sals) / len(sals) if sals else 0
        fw_stats.append((sk, cnt, avg_sal))
        if len(fw_stats) >= 50:
            break

fw_stats.sort(key=lambda x: -x[1])
print(f"  {'框架/工具':<25s} {'出现次数':>6s}  {'占比':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*6} {'-'*6} {'-'*8}")
for name, cnt, avg_sal in fw_stats[:30]:
    pct = cnt / len(rows) * 100
    print(f"  {name[:25]:25s} {cnt:>6,}  {pct:>5.1f}%  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 4. AI/ML 技能
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【4. AI/机器学习/数据技能】")
AI_SKILLS = [
    'Python', 'TensorFlow', 'PyTorch', 'Keras', 'Scikit-learn', 'scikit-learn',
    '机器学习', '深度学习', '自然语言处理', 'NLP', '计算机视觉', 'CV',
    '大模型', 'LLM', 'GPT', 'Transformer', 'BERT',
    '算法', '推荐算法', '搜索算法', '广告算法',
    '数据挖掘', '数据科学', '数据分析', '数据工程',
    'Pandas', 'NumPy', 'Matplotlib', 'Seaborn',
    'Hadoop', 'Spark', 'Flink', 'Hive', 'HBase',
    'SQL', 'MySQL', 'PostgreSQL', 'MongoDB', 'Redis',
    '模型训练', '模型部署', '模型优化', '模型压缩',
    '强化学习', 'RL', '生成式AI', 'AIGC', 'Stable Diffusion',
    '图像识别', '语音识别', '目标检测', '语义分割',
    'AI', '人工智能', 'langchain', 'LangChain', 'LlamaIndex',
    'RAG', '向量数据库', '知识图谱',
]
ai_stats = []
ai_total = 0
for ai_sk in AI_SKILLS:
    cnt = skill_counter.get(ai_sk, 0)
    if cnt == 0:
        continue
    ai_total += cnt
    sals = skill_salaries.get(ai_sk, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    ai_stats.append((ai_sk, cnt, avg_sal))
ai_stats.sort(key=lambda x: -x[1])
print(f"  {'AI/ML技能':<25s} {'出现次数':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*6} {'-'*8}")
for name, cnt, avg_sal in ai_stats[:30]:
    print(f"  {name[:25]:25s} {cnt:>6,}  {avg_sal:>7.1f}k")

# Count listings with at least one AI skill
ai_set = set(AI_SKILLS)
ai_listing_count = 0
for skills_str, _, _ in rows:
    items = set(s.strip() for s in skills_str.split('|') if s.strip())
    if items & ai_set:
        ai_listing_count += 1
print(f"\n  含AI/ML技能的职位数: {ai_listing_count:,} ({ai_listing_count/len(rows)*100:.1f}%)")

# ═══════════════════════════════════════════
# 5. 云原生/DevOps 技能
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【5. 云原生 / DevOps / 基础设施】")
CLOUD_SKILLS = [
    'Docker', 'Kubernetes', 'K8s', 'Jenkins', 'CI/CD', 'DevOps',
    'AWS', 'Azure', 'GCP', '阿里云', '腾讯云', '华为云', '云原生',
    'Terraform', 'Ansible', 'Prometheus', 'Grafana', 'ELK',
    'Nginx', 'HAProxy', 'Istio', 'Envoy',
    'Git', 'GitLab', 'GitHub', 'GitHub Actions',
    'Linux', 'Shell', 'Bash',
    '微服务', '服务网格', 'Service Mesh',
    'ZooKeeper', 'Nacos', 'Consul', 'Etcd',
    'Maven', 'Gradle', 'Ant',
    'SRE', 'AIOps',
]
cloud_stats = []
cloud_total = 0
for csk in CLOUD_SKILLS:
    cnt = skill_counter.get(csk, 0)
    if cnt == 0:
        continue
    cloud_total += cnt
    sals = skill_salaries.get(csk, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    cloud_stats.append((csk, cnt, avg_sal))
cloud_stats.sort(key=lambda x: -x[1])
print(f"  {'云原生技能':<25s} {'出现次数':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*6} {'-'*8}")
for name, cnt, avg_sal in cloud_stats[:25]:
    print(f"  {name[:25]:25s} {cnt:>6,}  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 6. 前端技能
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【6. 前端/移动端技能】")
FE_SKILLS = [
    'React', 'Vue', 'Vue.js', 'Angular', 'jQuery', 'Bootstrap',
    'JavaScript', 'TypeScript', 'HTML', 'HTML5', 'CSS', 'CSS3',
    'Node.js', 'Express', 'Koa', 'NestJS', 'Next.js', 'Nuxt.js',
    'Webpack', 'Vite', 'Babel', 'ESLint', 'Prettier',
    '小程序', '微信小程序', 'uniapp', 'uni-app', 'Flutter',
    'React Native', 'Electron', 'Taro',
    'Android', 'iOS', 'Swift', 'Kotlin', 'Objective-C',
    'Sass', 'Less', 'Tailwind', 'Ant Design', 'Element UI',
    'Canvas', 'WebGL', 'Three.js', 'D3.js', 'ECharts',
    'WebRTC', 'WebSocket', 'SSE',
]
fe_stats = []
for fsk in FE_SKILLS:
    cnt = skill_counter.get(fsk, 0)
    if cnt == 0:
        continue
    sals = skill_salaries.get(fsk, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    fe_stats.append((fsk, cnt, avg_sal))
fe_stats.sort(key=lambda x: -x[1])
print(f"  {'前端/移动端':<25s} {'出现次数':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*6} {'-'*8}")
for name, cnt, avg_sal in fe_stats[:25]:
    print(f"  {name[:25]:25s} {cnt:>6,}  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 7. 数据库技能
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【7. 数据库技能】")
DB_SKILLS = [
    'MySQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Oracle', 'SQL Server',
    'Elasticsearch', 'ES', 'Cassandra', 'HBase', 'ClickHouse',
    'TiDB', 'OceanBase', 'Neo4j', '图数据库',
    'SQLite', 'MariaDB', 'DynamoDB', 'InfluxDB', 'TDengine',
]
db_stats = []
for dsk in DB_SKILLS:
    cnt = skill_counter.get(dsk, 0)
    if cnt == 0:
        continue
    sals = skill_salaries.get(dsk, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    db_stats.append((dsk, cnt, avg_sal))
db_stats.sort(key=lambda x: -x[1])
print(f"  {'数据库':<25s} {'出现次数':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*6} {'-'*8}")
for name, cnt, avg_sal in db_stats[:20]:
    print(f"  {name[:25]:25s} {cnt:>6,}  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 8. 技能组合共现分析 Top
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【8. 技能共现 Top 对】")
pair_counter = Counter()
for skills_str, _, _ in rows:
    if not skills_str:
        continue
    skills = list(set(s.strip() for s in skills_str.split('|') if s.strip() and is_real_skill(s.strip())))
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            pair = (skills[i], skills[j])
            pair_counter[pair] += 1

print(f"  {'技能A':<20s} {'技能B':<20s} {'共现次数':>8s}")
print(f"  {'-'*20} {'-'*20} {'-'*8}")
for (a, b), cnt in pair_counter.most_common(25):
    print(f"  {a[:20]:20s} {b[:20]:20s} {cnt:>8,}")

# ═══════════════════════════════════════════
# 9. 技术栈深度分布
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【9. 技能标签数量分布 (每岗位)】")
tag_count_counter = Counter()
for skills_str, _, _ in rows:
    if not skills_str:
        continue
    skills = [s.strip() for s in skills_str.split('|') if s.strip() and is_real_skill(s.strip())]
    tag_count_counter[len(skills)] += 1
print(f"  {'标签数':>6s} {'岗位数':>6s}  {'占比':>6s}")
print(f"  {'-'*6} {'-'*6} {'-'*6}")
for k in sorted(tag_count_counter.keys()):
    cnt = tag_count_counter[k]
    pct = cnt / len(rows) * 100
    bar = '█' * max(1, int(pct))
    print(f"  {k:>6d} {cnt:>6,}  {pct:>5.1f}% {bar}")
avg_tags = sum(k * v for k, v in tag_count_counter.items()) / sum(tag_count_counter.values())
print(f"\n  平均技能标签数: {avg_tags:.1f}")

# ═══════════════════════════════════════════
# 10. 技能 × 城市差异
# ═══════════════════════════════════════════
print("\n" + "─" * 60)
print("【10. Top 技能城市偏好 (该技能在各城市的集中度)】")
cities = ['北京', '上海', '深圳', '杭州', '广州', '成都', '武汉']
for sk, _ in top_skills[:10]:
    print(f"\n  [{sk}]")
    city_dist = skill_city.get(sk, Counter())
    total_sk = sum(city_dist.values())
    if total_sk == 0:
        continue
    city_pcts = []
    for city in cities:
        cc = city_dist.get(city, 0)
        city_pcts.append((city, cc))
    city_pcts.sort(key=lambda x: -x[1])
    line = '    '
    for city, cc in city_pcts[:5]:
        line += f"{city}:{cc:>5,}({cc/total_sk*100:.0f}%)  "
    print(line)

print("\n" + "=" * 70)
print("=== 技能分布分析完成 ===")
conn.close()