import streamlit as st
import google.generativeai as genai
import os
from dotenv import load_dotenv
import tempfile
import time

# --- 1. 配置与初始化 ---

# 加载 .env 文件中的 API Key (安全起见，不要把 Key 硬编码在代码里)
# 在项目根目录下创建一个 .env 文件，内容为：GOOGLE_API_KEY=你的API密钥
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("请设置 GOOGLE_API_KEY 环境变量或在 .env 文件中配置。")
    st.stop()

# 配置 Gemini API
genai.configure(api_key=api_key)

# --- 2. 定义 Prompts (核心灵魂) ---

# 【System Prompt】：确立 AI 的专家人设和分析原则
SYSTEM_INSTRUCTION = """
你是一位拥有15年经验的华尔街卖方分析师（Sell-side Analyst），专精于TMT（科技、媒体、通信）和消费行业。你的工作是阅读上市公司的财报（10-K/10-Q），并为机构投资者撰写深度研报。

你的分析风格必须遵循以下原则：
1. 数据驱动 (Data-Driven): 所有结论必须有具体的数字支持。
2. 客观批判 (Critical & Objective): 不要只复述管理层的乐观言论。你需要寻找数据与叙述之间的矛盾，挖掘潜在风险（例如：库存积压、利润率下滑、现金流恶化）。
3. 结构化输出 (Structured Output): 使用清晰的 Markdown 格式。
4. 禁止幻觉 (No Hallucination): 如果财报中未提及某项数据，明确说明“未披露”，严禁编造。
5. 对比视角 (Comparative View): 总是关注同比 (YoY) 和环比 (QoQ) 的变化趋势。
"""

# 【User Prompt Template】：定义分析报告的结构框架
# 这里的 {ticker} 和 {period} 是占位符，稍后会替换
USER_PROMPT_TEMPLATE = """
### 任务目标
请详细分析我上传的这项 **{ticker}** 的 **{period}** 财报文件。

### 分析要求
请按照以下框架生成一份专业研报（请确保使用 Markdown 格式以便阅读）：

#### 1. 核心财务数据速览 (Executive Summary)
* **营收 (Revenue):** [数值] (YoY %, QoQ %) - *评价：超预期/符合/不及预期*
* **净利润/每股收益 (EPS):** [数值] (YoY %)
* **毛利率 (Gross Margin):** [数值] (与上季度/去年同期相比变化 [bp])
* **自由现金流 (FCF):** [数值] - *简评现金流健康度*

#### 2. 关键业务线深挖 (Segment Deep Dive)
* 分析各核心分部（Segment）的表现。哪个部门是增长引擎？哪个部门在拖后腿？
* 请寻找财报中关于未来增长点（如 AI 投入、新市场拓展）的具体数据和描述。

#### 3. 风险与负面因素排查 (Risks & Headwinds Check)
* **寻找“魔鬼细节”**：
    * 是否存在应收账款或库存增速显著快于营收增速的情况？
    * 运营费用 (OpEx) 是否失控？
* 宏观逆风（如汇率、通胀、供应链）的具体量化影响有哪些？

#### 4. 管理层指引与语调 (Guidance & Sentiment)
* 下季度/全年指引范围：[数值] - *评价指引是强劲还是疲软*
* **总体语调判定**：基于文件内容，管理层对未来的态度是“谨慎乐观”、“强劲自信”还是“保守防御”？请引用原文里的关键表述来支持你的判断。

#### 5. 分析师关键结论 (Key Takeaway)
* 一句话总结：这份财报是 Bullish (重大利多), Mildly Bullish (温和利多), Neutral (中性), Mildly Bearish (温和利空), 还是 Bearish (重大利空)？
* **核心关注点**：作为机构投资者，接下来一个季度最应该关注的一个指标或风险是什么？
"""

# --- 3. Streamlit 页面构建 ---

st.set_page_config(page_title="AI 专业财报分析师", page_icon="📈", layout="wide")

st.title("📈 AI 专业美股财报分析助手")
st.markdown("上传 PDF 财报 (10-K/10-Q)，基于 Gemini 1.5 Pro 超长上下文能力，生成华尔街级别的深度分析报告。")

# 侧边栏：输入基本信息
with st.sidebar:
    st.header("1. 信息输入")
    ticker_input = st.text_input("公司股票代码 (Ticker)", value="例如: NVDA, AAPL", help="这将用于 Prompt 中指代公司")
    period_input = st.text_input("财报周期 (Period)", value="例如: FY2025 Q1", help="指明是哪个季度的财报")
    st.divider()
    st.info("提示：Gemini 1.5 Pro 分析长文档需要时间，通常需要 1-3 分钟，请耐心等待。")

# 主区域：文件上传
st.header("2. 上传财报 PDF")
uploaded_file = st.file_uploader("请选择 PDF 文件 (支持超大文件)", type=['pdf'])

# 开始分析按钮
if uploaded_file is not None and ticker_input and period_input:
    if st.button("🚀 开始深度分析", type="primary"):
        # 显示加载动画
        with st.spinner(f"正在深入研读 {ticker_input} 的财报，这可能需要几分钟，请稍候..."):
            try:
                # --- 核心处理流程 ---
                
                # 1. 创建临时文件保存上传的 PDF (Gemini SDK 需要文件路径)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name

                # 2. 将文件上传到 Google Gemini 服务器
                # Gemini 1.5 可以直接“看”懂 PDF 文件，包括里面的表格，效果比单纯提取文本更好
                upload_start_time = time.time()
                gemini_file = genai.upload_file(path=tmp_file_path, mime_type="application/pdf")
                st.toast(f"文件上传至 Gemini 成功 (耗时 {time.time() - upload_start_time:.1f}s)，开始生成分析...", icon="✅")
                
                # 3. 初始化模型，载入我们的“分析师人设” (System Instruction)
                # 设置 temperature=0.1 以确保分析的客观性和准确性
                model = genai.GenerativeModel(
                    model_name="gemini-1.5-pro-latest",
                    system_instruction=SYSTEM_INSTRUCTION,
                    generation_config={"temperature": 0.1}
                )

                # 4. 组合 User Prompt 并发起请求
                # 替换模板中的占位符
                final_user_prompt = USER_PROMPT_TEMPLATE.format(ticker=ticker_input, period=period_input)
                
                # 向模型发送 Prompt 和文件
                response = model.generate_content([final_user_prompt, gemini_file])

                # 5. 展示结果
                st.success("分析报告生成完毕！")
                st.divider()
                # 使用 markdown 渲染漂亮的报告
                st.markdown(response.text)

                # --- 清理工作 ---
                # 删除本地临时文件
                os.unlink(tmp_file_path)
                # 删除 Gemini 服务器上的文件 (好习惯，虽然它们也会自动过期)
                genai.delete_file(gemini_file.name)

            except Exception as e:
                st.error(f"分析过程中发生错误: {e}")
                st.warning("请检查 API Key 是否正确，网络连接是否正常（需要能访问 Google API）。")

elif uploaded_file is None:
    st.info("请先上传 PDF 文件。")
elif not ticker_input or not period_input:
    st.warning("请在侧边栏填写股票代码和财报周期。")

# 页脚
st.divider()
st.caption("Powered by Google Gemini 1.5 Pro & Streamlit. 本报告仅供参考，不构成投资建议。")
