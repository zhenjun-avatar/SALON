import html
import zipfile


TEXT = """多猫舍 AI 助理平台（精简版一页架构文案）

版本定位（V1）：先实现“客户服务闭环 + 自动记账 + 图片视频健康识别”，确保低成本、可快速上线、可持续迭代。

1) 建设目标
- 企业微信自动接待，完成咨询、预约、下单、售后基础闭环
- 财务仅做自动记账，统一沉淀收入/退款/平台费用流水
- 健康模块仅做图片/视频自动采集与自动识别健康状态
- 全链路可追溯（客户、猫、订单、账务、健康记录）

2) 精简总体架构
[渠道层]
企业微信 / 美团 / 淘宝 / 支付渠道 / 摄像头相机
        |
        v
[接入层]
API Gateway + Webhook + 鉴权 + 幂等
        |
        v
[核心业务层]
CRM | 会话AI | 预约订单 | 财务自动记账 | 健康自动识别
        |
        v
[AI与规则层]
LLM意图识别与回复 | RAG知识库 | 图像视频识别模型 | 风险规则
        |
        v
[数据与基础设施层]
MySQL | Redis | RabbitMQ | Celery | MinIO/OSS | 监控日志

3) 模块职责（V1范围）
- CRM：客户档案、猫档案、客户-多猫关系、授权状态
- 会话AI（企业微信）：意图识别、槽位采集、工具调用、自动回复、转人工
- 预约与订单：预约/改期/取消、统一订单号、支付回调、履约状态
- 财务（仅自动记账）：自动记录收入、退款、平台费用，形成统一流水账
- 健康（仅图片视频识别）：摄像头/相机自动采集 -> 模型识别 -> 输出健康状态（正常/关注/高风险）

4) 关键流程（简版）
- 会话闭环：客户消息 -> AI识别意图 -> 调预约/订单/知识库 -> 回复结果
- 自动记账：支付/退款/平台扣费事件 -> 自动写入 finance_ledger
- 健康识别：自动采集图片视频 -> 异步识别 -> 回写猫档案 -> 高风险告警人工

5) V1技术栈
- 后端：FastAPI
- 数据：MySQL + Redis
- 异步：RabbitMQ + Celery
- 存储：MinIO/OSS
- AI：LLM（Qwen/DeepSeek/OpenAI兼容）+ RAG（pgvector/Milvus）
- 视觉：OpenCV + FFmpeg + 推理服务（云API或本地）

6) 边界与合规
- 财务V1不做审批流和复杂经营分析，仅自动记账
- 健康V1不做医疗诊断，仅做风险识别与提醒
- 固定声明：“识别结果仅供护理参考，不构成医疗诊断。”
- 高风险（如疑似急性异常）必须转人工并建议线下兽医

7) 交付价值
- 快速上线：业务先跑通
- 成本可控：优先自动化高频环节
- 可迭代：后续可平滑升级财务分析、问诊流程与模型能力

8) 成本估算（4-5家店，V1）
一次性开发成本：约 11.5万 ~ 22万
- CRM：2万 ~ 4万
- 会话AI：3万 ~ 6万
- 预约订单：3万 ~ 5万
- 财务自动记账：1.5万 ~ 3万
- 健康识别（图像视频）：2万 ~ 4万

硬件成本（健康采集）：
- 单店（2摄像头+1迷你主机）：2500 ~ 4000
- 4-5家店合计：1万 ~ 2万

月度运行成本：约 2800 ~ 1万/月
- 云资源+数据库+缓存：1000 ~ 2500/月
- 对象存储：300 ~ 1000/月
- LLM调用：1000 ~ 4000/月
- 图像视频识别：500 ~ 2500/月

首年总投入参考：约 16万 ~ 36万（开发+硬件+12个月运行）
"""


def paragraph(line: str) -> str:
    escaped = html.escape(line)
    if not escaped:
        return "<w:p/>"
    return (
        '<w:p><w:r><w:t xml:space="preserve">'
        + escaped
        + "</w:t></w:r></w:p>"
    )


body = "".join(paragraph(line) for line in TEXT.split("\n"))

document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:w10="urn:schemas-microsoft-com:office:word" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"""

content_types_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

output = "多猫舍AI助理平台_V1_架构与成本.docx"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
    docx.writestr("[Content_Types].xml", content_types_xml)
    docx.writestr("_rels/.rels", rels_xml)
    docx.writestr("word/document.xml", document_xml)

print(output)
