"""生成双语文字版 PDF：data/hr_policy_bilingual.pdf（reportlab，STSong-Light 中文字体）。"""
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "hr_policy_bilingual.pdf")

BLOCKS = [
    ("考勤制度 Attendance",
     "工作时间 9:00-18:00（午休 1 小时），弹性打卡允许 8:00-10:30 之间任意时间打上班卡，工作满 8 小时即可下班。"
     "Working hours are 9:00-18:00 with a 1-hour lunch break; flex check-in between 8:00 and 10:30 is allowed as long as 8 hours are worked."),
    ("加班与调休 Overtime & Comp Time",
     "加班需事前在 OA 提交并经主管批准；工作日加班 1:1 调休，周末加班 1:2 调休；调休有效期 6 个月。法定节假日加班按 3 倍工资发放。"
     "Pre-approved overtime converts to comp time at 1:1 on weekdays and 1:2 on weekends, valid for 6 months; public-holiday work pays triple wages."),
    ("远程办公 Remote Work",
     "员工每月可申请最多 4 天远程办公，需提前 1 天在系统报备并保证在线时段 10:00-16:00 可响应。高管与客服岗位暂不适用。"
     "Up to 4 remote days per month, filed 1 day ahead; must stay reachable 10:00-16:00. Not applicable to executive and support-desk roles."),
    ("补充商业保险 Supplementary Insurance",
     "公司入职当月为全体正式员工投保补充医疗险（门诊 2 万/年，住院 20 万/年）与意外险 50 万；子女 18 岁以下可附加投保，保费公司承担 50%。"
     "The company provides supplementary medical cover (CNY 20k outpatient / 200k inpatient per year) and CNY 500k accident insurance from the onboarding month."),
]


def main():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = SimpleDocTemplate(OUT, pagesize=A4, title="HR Policy Bilingual")
    zh = ParagraphStyle("zh", fontName="STSong-Light", fontSize=11, leading=16, alignment=TA_LEFT)
    h = ParagraphStyle("h", parent=zh, fontSize=14, leading=20, spaceBefore=12)
    story = [Paragraph("人力资源部制度摘编（双语）HR Policy Extract (Bilingual)", h)]
    for title, body in BLOCKS:
        story.append(Paragraph(title, h))
        story.append(Paragraph(body, zh))
        story.append(Spacer(1, 8))
    doc.build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
