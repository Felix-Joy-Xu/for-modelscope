"""BOSS 数据库 — 全量 JD 词频分析"""
import sqlite3
import jieba
import re
from collections import Counter

DB = r'D:\hiring_data\boss_api\boss_jobs.db'

print("=" * 70)
print("=== BOSS 直聘 — 全量 JD 词频分析 ===")
print("=" * 70)

# ── 加载数据 ──
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT jd_text, jd_len, salary_avg_k, city, jobName
    FROM jobs 
    WHERE jd_text IS NOT NULL AND jd_text != '' AND jd_len > 30
""")
rows = cur.fetchall()
print(f"\n有效 JD 样本: {len(rows):,}")
print(f"平均 JD 长度: {sum(r['jd_len'] for r in rows)/len(rows):.0f} 字符\n")

# ── 停用词 — 中文通用 + JD 特有 ──
STOP_WORDS = set("""
的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你
会 着 没有 看 好 自己 这 他 她 它 们 那 些 什么 而 为 所以 因为
但是 可以 这个 如果 虽然 已经 还是 或者 等 及 与 并 根据
对 于 中 从 以 将 能 能够 具有 进行 使用 负责 参与 完成 包括
需要 要求 具备 熟悉 了解 掌握 相关 以上 以下 优先 加分 经验
任职 岗位 职责 要求 工作 能力 做好 项目 业务 产品 技术 数据 系统
服务 平台 部门 团队 公司 提供 支持 实现 通过 设计 开发 测试 运营
维护 管理 保障 推动 负责 解决 提升 优化 迭代 分析 处理 跟进 落实
沟通 协调 组织 计划 执行 落地 探索 研究 落地
年 月 日 时 分 秒 个 次 件 项 名 位 种 类 元 万 亿
高 大 多 少 新 旧 好 强 弱 快 慢 长 短 前 后 左 右 内 外
欢迎 加入 我们 您 请 让 各位 大家 如 如有 感兴趣 邮箱 简历
投递 方式 地址 电话 微信 qq 联系 咨询 详情 更多 长期 有效
长期 有效 福利 待遇 薪资 面议 晋升 空间 发展 前景 文化 氛围
岗位职责 任职要求 岗位要求 招聘 描述 职位 工作职责 工作内容
职能类别 关键字 加分项 亮点 优先考虑 具备以下 具有以下
1 2 3 4 5 6 7 8 9 0
a b c d e f g h i j k l m n o p q r s t u v w x y z
""".split())

# 额外 — 纯数字、纯字母、单字
SINGLE_CHARS = set('的一了在是我不人他有这个上中下前后左右多少大小好坏来去说得着看也就会可以为而或但从这那什么怎么哪')

def is_valid_word(w):
    w = w.strip()
    if len(w) < 2:
        return False
    if w in STOP_WORDS:
        return False
    # 纯数字
    if re.fullmatch(r'\d+', w):
        return False
    # 纯英文字母 <= 2 字符
    if re.fullmatch(r'[a-zA-Z]{1,2}', w):
        return False
    # 纯标点
    if re.fullmatch(r'[\W_]+', w):
        return False
    return True

# ── 分词 + 统计 ──
print("分词中...")
word_counter = Counter()
high_sal_words = Counter()  # 薪资 > P75
high_sal_total = 0
city_words = {}  # city -> Counter

# 先算薪资分位
all_sals = [r['salary_avg_k'] for r in rows if r['salary_avg_k'] and r['salary_avg_k'] > 0]
all_sals.sort()
p75 = all_sals[int(len(all_sals) * 0.75)]
print(f"薪资 P75: {p75:.1f}k")

for i, r in enumerate(rows):
    if i % 10000 == 0 and i > 0:
        print(f"  处理进度: {i:,} / {len(rows):,}")
    text = r['jd_text']
    salary = r['salary_avg_k']
    city = r['city']
    
    # 清洗文本
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', ' ', text)  # 邮箱
    text = re.sub(r'https?://\S+', ' ', text)  # URL
    text = re.sub(r'[^\u4e00-\u9fff\w]', ' ', text)  # 去特殊符，保留中英文
    
    words = jieba.lcut(text)
    valid_words = [w.strip().lower() for w in words if is_valid_word(w.strip())]
    
    word_counter.update(valid_words)
    
    # 高薪 JD
    if salary and salary > 0 and salary >= p75:
        high_sal_words.update(valid_words)
        high_sal_total += 1
    
    # 按城市
    if city:
        if city not in city_words:
            city_words[city] = Counter()
        city_words[city].update(valid_words)

print(f"\n分析完成:")
print(f"  总词数: {sum(word_counter.values()):,}")
print(f"  唯一词数: {len(word_counter):,}")
print(f"  高薪 JD 数(>={p75:.0f}k): {high_sal_total:,}")
top_words = word_counter.most_common(200)

# ═══════════════════════════════════════════
# 1. 全量词频 Top 60 (中文)
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【1. JD 中文词频 Top 60】")
print(f"  {'词语':<20s} {'次数':>7s}  {'占比':>6s}  {'可视化':>10s}")
print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*10}")
total_jd = len(rows)
for i, (word, cnt) in enumerate(top_words):
    if i >= 60:
        break
    pct = cnt / total_jd * 100
    bar = '█' * max(1, int(cnt / top_words[0][1] * 50))
    print(f"  {word[:20]:20s} {cnt:>7,d}  {pct:>5.1f}%  {bar}")

# ═══════════════════════════════════════════
# 2. 技术技能词频 Top 50
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【2. 技术技能词频 Top 50】")
TECH_WORDS = {
    # 语言
    'python', 'java', 'javascript', 'typescript', 'golang', 'go', 'c++', 'cpp', 'c', 'c#',
    'php', 'rust', 'ruby', 'scala', 'kotlin', 'swift', 'matlab', 'r', 'shell', 'bash',
    'node', 'nodejs', 'node.js',
    # 框架
    'spring', 'springboot', 'springcloud', 'mybatis', 'hibernate', 'dubbo', 'netty',
    'django', 'flask', 'fastapi', 'tornado', 'express', 'nestjs',
    'react', 'vue', 'angular', 'jquery', 'bootstrap',
    'pytorch', 'tensorflow', 'paddlepaddle', 'keras', 'scikit-learn',
    'langchain', 'llamaindex', 'transformers',
    # 数据库
    'mysql', 'redis', 'postgresql', 'mongodb', 'oracle', 'elasticsearch', 'hbase',
    'sqlite', 'mariadb', 'clickhouse', 'tidb', 'neo4j', 'cassandra',
    # 云原生
    'docker', 'kubernetes', 'k8s', 'jenkins', 'nginx', 'devops', 'cicd', 'ci/cd',
    'istio', 'envoy', 'consul', 'etcd', 'zookeeper', 'nacos',
    # 大数据
    'hadoop', 'spark', 'flink', 'hive', 'kafka', 'storm', 'airflow',
    # 基础
    'linux', 'git', 'maven', 'gradle', 'webpack', 'vite',
    'grpc', 'graphql', 'restful', 'websocket', 'protobuf',
    # 小程序/跨端
    'flutter', 'reactnative', 'electron', 'uniapp', 'taro', 'weex',
    'android', 'ios', 'sdk',
    # AI/ML 中文
    '机器学习', '深度学习', '自然语言处理', '计算机视觉', '大模型', '强化学习',
    '神经网络', '决策树', '随机森林', '逻辑回归', '支持向量机', '卷积神经网络', '循环神经网络',
    '目标检测', '语义分割', '图像识别', '语音识别', 'nlp', 'cv', 'llm',
    '生成式', 'aigc', 'rag', 'stable diffusion', 'diffusion',
    '向量数据库', '知识图谱', '数据挖掘', '数据科学', '数据分析', '数据仓库',
    '特征工程', '模型训练', '模型部署', '模型优化', '模型压缩', '微调',
    '多模态', 'transformer', 'bert', 'gpt',
    # Web 相关
    'html', 'html5', 'css', 'css3', 'ajax', 'json', 'xml', 'yaml',
    'sass', 'less', 'tailwind', 'webgl', 'canvas', 'svg', 'd3',
    'echarts', 'threejs', 'antd', 'ant design', 'elementui', 'element',
    '小程序', '微信小程序', '公众号',
    # 通信/协议
    'tcp', 'udp', 'http', 'https', 'websocket', 'rpc', 'mqtt',
    # 其他
    'jvm', 'gc', 'nio', 'aio', 'bio', 'guava',
    'junit', 'mockito', 'testng', 'selenium', 'appium',
    'unittest', 'pytest',
    'numpy', 'pandas', 'matplotlib', 'opencv', 'huggingface',
    'scipy', 'sklearn',
    'sentinel', 'gateway',
    'prometheus', 'grafana', 'elk', 'efk',
    'rocketmq', 'rabbitmq', 'activemq', 'pulsar',
    'svm', 'knn', 'xgboost',
    'ddr', 'pcie', 'arm', 'x86', 'mcu', 'fpga', 'rtos',
    'llvm', 'gcc', 'cmake', 'makefile', 'gitlab', 'github',
    'ansible', 'terraform', 'puppet', 'saltstack',
    'axios', 'fetch',
    'nextjs', 'nuxtjs', 'svelte',
}
tech_freq = {}
for w, cnt in word_counter.most_common():
    wl = w.lower().replace('.', '').replace(' ', '').replace('-', '').replace('_', '')
    if w in TECH_WORDS or wl in TECH_WORDS or w.lower() in TECH_WORDS:
        tech_freq[w] = cnt
tech_sorted = sorted(tech_freq.items(), key=lambda x: -x[1])
print(f"  {'技术词':<25s} {'次数':>7s}  {'占比':>6s}  {'薪资均值':>8s}")
print(f"  {'-'*25} {'-'*7} {'-'*6} {'-'*8}")
# calc avg salary per tech word
tech_salaries = {}
for r in rows:
    text = r['jd_text']
    salary = r['salary_avg_k']
    text_lower = text.lower()
    for tech, _ in tech_sorted[:50]:
        if tech.lower() in text_lower:
            if tech not in tech_salaries:
                tech_salaries[tech] = []
            if salary and salary > 0:
                tech_salaries[tech].append(salary)
for tech, cnt in tech_sorted[:50]:
    sals = tech_salaries.get(tech, [])
    avg_sal = sum(sals) / len(sals) if sals else 0
    pct = cnt / total_jd * 100
    print(f"  {tech[:25]:25s} {cnt:>7,d}  {pct:>5.1f}%  {avg_sal:>7.1f}k")

# ═══════════════════════════════════════════
# 3. 高频词分类展示
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【3. 高频词按概念分类】")

CATEGORIES = {
    "🎓 学历": ['本科', '硕士', '博士', '大专', '本科以上', '本科及以上', '硕士以上', '全日制', '985', '211', '一本', '双一流', '留学生', '海外'],
    "⏳ 经验": ['3年', '5年', '1年', '2年', '年经验', '年以上', '实习', '应届', '在校', '毕业生', '经验不限', '不限经验', '三年', '五年'],
    "🏢 软实力": ['沟通', '协作', '团队', '逻辑', '学习', '英文', '英语', '文档', '主动性', '责任心', '抗压', '自驱', '独立', '创新', '解决问题'],
    "📐 架构": ['架构', '分布式', '微服务', '高并发', '高可用', '可扩展', '系统设计', '设计模式', '组件化', '模块化', 'DDD', '领域驱动'],
    "🌐 业务领域": ['电商', '金融', '游戏', 'AI', '人工智能', '大数据', '云计算', '直播', '短视频', '物联网', 'IoT', '区块链', '自动驾驶', '芯片', '医疗', '教育', '社交', '支付', '广告', '推荐', '搜索'],
    "🔒 安全": ['安全', '加密', '漏洞', '防火墙', '渗透', '安全测试', '信息安全', 'SDL', '隐私'],
    "📊 数据": ['数据', '大数据', '数据库', '数仓', '数据仓库', '数据湖', 'ETL', 'OLAP', 'OLTP', '数据中台'],
    "🔧 测试": ['测试', '自动化测试', '单元测试', '集成测试', '性能测试', '接口测试', '功能测试', '回归测试', '测试用例', '测试计划', 'QA'],
    "📱 移动端": ['Android', 'iOS', 'Flutter', 'React Native', '小程序', '微信小程序', 'uniapp', '移动端', '手机', 'APP', 'App'],
    "🤖 AI专项": ['大模型', 'LLM', 'GPT', 'ChatGPT', '深度学习', '机器学习', '神经网络', 'NLP', 'CV', '自然语言处理', '计算机视觉', '强化学习', '推荐系统', '搜索', '广告', 'AIGC', '生成式', 'RAG', '向量数据库', '模型', '算法'],
}

for cat_name, keywords in CATEGORIES.items():
    print(f"\n  [{cat_name}]")
    cat_items = []
    for kw in keywords:
        cnt = word_counter.get(kw, 0) + word_counter.get(kw.lower(), 0)
        if cnt > 0:
            cat_items.append((kw, cnt))
    cat_items.sort(key=lambda x: -x[1])
    line = "    "
    for kw, cnt in cat_items[:10]:
        pct = cnt / total_jd * 100
        line += f"{kw}({cnt:,},{pct:.1f}%)  "
    print(line)

# ═══════════════════════════════════════════
# 4. 高薪 JD (>=P75) 独有词 Top 30
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print(f"【4. 高薪 JD (≥{p75:.0f}k) 特征词 Top 30】")
print("     (在高薪JD中出现频率远超普通JD的词)")
# 计算普通JD词频
low_sal_words = Counter()
low_sal_total = 0
for r in rows:
    salary = r['salary_avg_k']
    if salary and salary > 0 and salary < p75:
        low_sal_total += 1
        text = r['jd_text']
        text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', ' ', text)
        text = re.sub(r'https?://\S+', ' ', text)
        text = re.sub(r'[^\u4e00-\u9fff\w]', ' ', text)
        words = jieba.lcut(text)
        valid = [w.strip().lower() for w in words if is_valid_word(w.strip())]
        low_sal_words.update(valid)

print(f"    对比基数: 高薪JD {high_sal_total:,}  vs  普通JD {low_sal_total:,}")
print(f"    {'词语':<20s} {'高薪频次':>8s}  {'普通频次':>8s}  {'高/普比':>8s}")
print(f"    {'-'*20} {'-'*8} {'-'*8} {'-'*8}")
distinctive = []
for w, cnt in high_sal_words.most_common(500):
    if len(w) < 2:
        continue
    low_cnt = low_sal_words.get(w, 1)
    freq_high = cnt / high_sal_total
    freq_low = low_cnt / low_sal_total
    if freq_low > 0 and freq_high > 0.005:  # 高薪至少出现0.5%
        ratio = freq_high / freq_low
        if ratio > 1.3 and cnt > 100:  # 显著偏高
            distinctive.append((w, cnt, low_cnt, ratio))
distinctive.sort(key=lambda x: -x[3])
for w, hc, lc, ratio in distinctive[:30]:
    print(f"    {w[:20]:20s} {hc:>8,d}  {lc:>8,d}  {ratio:>7.1f}x")

# ═══════════════════════════════════════════
# 5. 城市独有词 Top 15
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【5. 各城市特征词 — 该城市 JD 中最独特的 Top 词汇】")
TOP_CITIES = ['北京', '上海', '深圳', '杭州', '广州', '成都', '武汉', '南京', '西安', '长沙']
for city in TOP_CITIES:
    if city not in city_words:
        continue
    cw = city_words[city]
    c_total = sum(cw.values())
    if c_total < 50000:
        continue
    all_total = sum(word_counter.values())
    city_distinct = []
    for w, cnt_c in cw.most_common(300):
        if len(w) < 2:
            continue
        cnt_all = word_counter.get(w, 1)
        freq_c = cnt_c / c_total
        freq_all = cnt_all / all_total
        if freq_c > 0.0003 and freq_all > 0:
            ratio = freq_c / freq_all
            if ratio > 1.3 and cnt_c > 30:
                city_distinct.append((w, cnt_c, ratio))
    city_distinct.sort(key=lambda x: -x[2])
    if city_distinct:
        line = f"  [{city}] "
        for w, cnt, ratio in city_distinct[:8]:
            line += f"{w}({ratio:.1f}x)  "
        print(line)

# ═══════════════════════════════════════════
# 6. co-occurrence: words that appear together
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【6. 高频词语义共现 — Top 共现对】")
# pick top 80 words
top80 = set(w for w, _ in top_words[:80])
pair_counter = Counter()
for i, r in enumerate(rows):
    if i % 15000 == 0 and i > 0:
        print(f"  共现计算进度: {i:,} / {len(rows):,}")
    text = r['jd_text']
    text = re.sub(r'[^\u4e00-\u9fff\w]', ' ', text)
    words = [w.strip().lower() for w in jieba.lcut(text) if w.strip() in top80]
    words = list(set(words))
    for p in range(len(words)):
        for q in range(p + 1, len(words)):
            pair_counter[(words[p], words[q])] += 1

print(f"  {'词语A':<12s} {'词语B':<12s} {'共现次数':>8s}")
print(f"  {'-'*12} {'-'*12} {'-'*8}")
for (a, b), cnt in pair_counter.most_common(30):
    print(f"  {a[:12]:12s} {b[:12]:12s} {cnt:>8,d}")

# ═══════════════════════════════════════════
# 7. 岗位名称词频
# ═══════════════════════════════════════════
print("\n" + "─" * 70)
print("【7. JD 标题词频 Top 30】")
job_counter = Counter(r['jobName'] for r in rows if r['jobName'])
print(f"  {'岗位名称':<35s} {'数量':>7s}  {'占比':>6s}")
print(f"  {'-'*35} {'-'*7} {'-'*6}")
for name, cnt in job_counter.most_common(30):
    pct = cnt / total_jd * 100
    print(f"  {name[:35]:35s} {cnt:>7,d}  {pct:>5.1f}%")

print("\n" + "=" * 70)
print("=== 全量 JD 词频分析完成 ===")
conn.close()