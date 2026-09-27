"""生成结构化真实语料：data/leave_management_policy.docx 与 data/remote_work_policy.md。

写作约束（刻意的）：
1. 内容按"真实公司制度长什么样"写，不许对着 eval/questions.jsonl 倒写——这是为了
   打破"语料照着答案写、题目照着语料写"的自证循环。
2. 已有语料覆盖过的数字一律不重写，只做交叉引用：年假天数（《员工手册》15/20/25 天）、
   加班倍率与调休有效期、远程办公天数配额与必响应时段、弹性打卡区间，都由
   《人力资源部制度摘编》/《员工手册》持有。本脚本只补充它们没有的事实
   （迟到认定、调休使用与延期、销假交接、设备补助、在岗细化）。
   第一版草稿曾把"迟到"定成"晚于 9:00"，与摘编里的弹性打卡 8:00–10:30 直接冲突，
   也把远程天数写成"每周 3 天"与"每月 4 天"打架——加第二份同主题文档时矛盾会立刻出现，
   这正是本条目要防的事，详见 docs/issue_diagnosis.md 问题六。
3. 故意包含：多级 Heading 样式、两张表格、一段超过 400 字的长条款（验证切块器的
   句边界切分与重叠）、一个围栏代码块（验证 md reader 的代码块路径）。

用法：python scripts/make_structured_docs.py
"""
import os

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

DOCX_OUT = os.path.join(DATA_DIR, "leave_management_policy.docx")
MD_OUT = os.path.join(DATA_DIR, "remote_work_policy.md")


def _set_cjk_font(doc):
    """给 Normal 样式挂中文字体，否则 Word 打开会显示成方块。"""
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def build_docx():
    doc = Document()
    _set_cjk_font(doc)

    doc.add_heading("假勤管理与加班调休制度（Attendance & Overtime Policy）", level=1)
    doc.add_paragraph(
        "文件编号：HR-POL-2026-007｜版本：V2.3｜生效日期：2026-04-01｜"
        "归口部门：人力资源部。本制度适用于公司全体正式员工与试用期员工，"
        "实习生参照执行。本制度与《员工手册》不一致时，以本制度为准；"
        "各类假期的天数标准仍以《员工手册》第一章为准，本制度不再重复约定。"
    )

    doc.add_heading("第一章 总则 Purpose", level=2)
    doc.add_paragraph(
        "为规范考勤管理、加班申请与调休核销流程，保障员工休息权与业务连续性，"
        "依据《职工带薪年休假条例》及国家有关工时规定，结合公司实际情况制定本制度。"
        "This policy standardizes attendance tracking, overtime approval and "
        "compensatory leave accounting for all employees."
    )

    doc.add_heading("第二章 考勤与打卡 Attendance", level=2)
    doc.add_paragraph("标准工作时间为周一至周五 9:00–18:00，午休 12:00–13:00 不计入工时。"
                      "弹性打卡沿用《人力资源部制度摘编》的规定：可在 8:00–10:30 之间任选时间打上班卡，"
                      "工作满 8 小时即可下班；本制度不重新定义弹性时段，只补充超出弹性范围后的认定与处理方式。"
                      "员工须在企业微信「考勤」应用中完成上下班打卡，外勤需在客户现场打卡并备注事由。")
    doc.add_heading("2.1 迟到与旷工认定 Late & Absence", level=3)
    doc.add_paragraph("下表中的「本人报备上班时间」指员工在考勤设置里登记的弹性起点。"
                      "考勤结果由 HR 每月 3 日前公示。")

    rows = [
        ("情形 Category", "认定标准 Threshold", "处理方式 Handling"),
        ("迟到 Late arrival", "晚于本人报备上班时间，且不超过 30 分钟", "当月累计 3 次以内不扣款，第 4 次起每次扣 50 元"),
        ("严重迟到 Serious late", "晚于本人报备上班时间 30 分钟以上、2 小时以内", "按半天事假计算，需直属主管书面确认"),
        ("早退 Early leave", "工时未满 8 小时且早于本人报备下班时间，无审批", "按半天事假计算"),
        ("旷工 Absence", "未打卡且无任何请假记录", "连续旷工 3 个工作日视为严重违纪，进入纪律处理流程"),
    ]
    table = doc.add_table(rows=0, cols=3)
    table.style = "Table Grid"
    for cells in rows:
        row = table.add_row().cells
        for i, val in enumerate(cells):
            row[i].text = val

    doc.add_heading("第三章 加班与调休 Overtime & Compensatory Leave", level=2)
    doc.add_heading("3.1 加班认定与倍率 Overtime Rates", level=3)
    doc.add_paragraph("所有加班须在 OA「加班申请」中事前提交，经直属主管批准后生效；"
                      "未经批准自行留岗不计入加班时长。工作日 1:1、周末 1:2 的换算口径沿用"
                      "《人力资源部制度摘编》，本表只补充调休使用期限与法定节假日的处理方式。")
    ot_rows = [
        ("加班类型 Type", "工资或调休倍率 Rate", "使用期限 Validity"),
        ("工作日晚间加班 Weekday", "1.0 倍，按调休处理", "自产生之日起 6 个月内使用"),
        ("周末加班 Weekend", "2.0 倍，可选调休或加班费", "自产生之日起 6 个月内使用"),
        ("法定节假日加班 Public holiday", "3.0 倍工资，支付加班费不得折抵为调休", "随当月工资发放，不产生调休余额"),
    ]
    ot_table = doc.add_table(rows=0, cols=3)
    ot_table.style = "Table Grid"
    for cells in ot_rows:
        row = ot_table.add_row().cells
        for i, val in enumerate(cells):
            row[i].text = val

    doc.add_heading("3.2 调休申请流程 Comp Leave Procedure", level=3)
    # 故意写一段超过 400 字的长条款，验证切块器的句边界切分与 50 字重叠
    doc.add_paragraph(
        "员工申请调休应在 HR 系统「假期管理」中选择「调休」类型，并填写预计使用日期与时长，"
        "系统会自动从本人的可调休余额中扣减。调休以半天为最小单位，不足半天的部分保留在余额中，"
        "不折算为现金。审批权限与年假一致：1 天以内由直属主管审批，超过 1 天需部门总监审批，"
        "超过 3 天需分管副总裁审批且至少提前 5 个工作日提交。主管应在收到申请后 2 个工作日内处理，"
        "逾期未处理视为同意，系统自动放行并将审批留痕记录为「超时默认通过」，事后如确因业务冲突"
        "需要撤回，由部门总监发起撤销并注明原因。调休余额在到期前 30 天、7 天各推送一次提醒，"
        "到期未使用的余额自动清零，不予折现，也不得结转至下一年度；因公司原因（如项目紧急抽调、"
        "客户现场封闭开发）导致员工确实无法在有效期内使用调休的，由部门总监在到期日前提交《调休"
        "延期申请单》，经人力资源部核准后可延长 3 个月，延期最多申请一次。员工离职时未使用的调休"
        "余额，公司按 2.0 倍日工资标准折算补偿，折算金额随最后一个月工资发放；已使用超过应得额度"
        "的部分不再向员工追偿，作为公司承担的管理成本处理。"
    )

    doc.add_heading("第四章 销假与委托 Check-out & Delegation", level=2)
    doc.add_heading("4.1 提前返岗与销假 Early Return", level=3)
    doc.add_paragraph("假期提前结束的员工应在返岗当日在 HR 系统办理销假，系统按实际休假天数重新核算，"
                      "多扣的天数退回余额。未办理销假且实际提前返岗的，按原批准天数计算，不做退还。")
    doc.add_heading("4.2 工作交接与委托 Handover", level=3)
    doc.add_paragraph("连续 3 天以上的假期（含调休）须在 OA 提交《工作交接单》，指定代理人并注明"
                      "在手事项、截止时间与联系人。代理人应在假期内对邮件与客户请求在 1 个工作日内响应；"
                      "涉及合同签署、付款审批等授权事项需提前完成系统授权配置。交接单未提交而直接休假，"
                      "造成的业务损失计入当期部门考核。")

    doc.save(DOCX_OUT)
    return DOCX_OUT


MD_TEXT = """# 远程办公与设备补助制度 Remote Work & Equipment Policy

文件编号：HR-POL-2026-011｜版本：V1.4｜生效日期：2026-06-01｜归口部门：人力资源部 / 信息技术部

本制度规定员工远程办公的申请方式、在岗要求与设备补助标准。
This policy covers remote work eligibility, availability requirements and equipment allowance.

## 一、适用范围 Eligibility

远程办公的天数配额沿用《人力资源部制度摘编》：员工每月可申请最多 4 天远程办公，
需提前 1 天在系统报备。本制度在此基础上补充岗位适用条件与设备补助标准。

- 入职满 3 个月且当季度绩效考核不低于 B 的正式员工；
- 高管与客服岗位不适用（与《摘编》一致）；运维等需值守内网系统的岗位按部门细则执行；
- 试用期员工如需远程，需部门总监单次审批，每月不超过 2 天。

## 二、额度与标准 Allowance

远程办公补贴按月随工资发放，无需发票；公司配发设备离职时须归还。

| 项目 Item | 标准 Amount | 说明 Note |
|---|---|---|
| 远程办公补贴 Remote allowance | 300 元/月 | 按月发放，无需发票 |
| 家庭网络费 Internet subsidy | 100 元/月 | 与远程补贴合并发放 |
| 人体工学椅 Ergonomic chair | 1500 元（一次性） | 需行政部统一采购 |
| 显示器 Monitor | 2000 元（一次性） | 公司资产，离职归还 |

## 三、在岗要求 Availability

必响应时段沿用《摘编》规定的 10:00–16:00。本制度追加两项细化要求：
远程日整体须在 9:30–18:00 保持企业微信在线；10:00–16:00 内消息响应不超过 15 分钟，
该时段之外不超过 60 分钟；会议邀请须提前 1 小时预约。
每月 4 天配额之内，连续远程办公不得超过 2 个工作日，
周三为全员到岗日（All-hands on-site day），部门活动与跨部门评审均安排在该日。

## 四、申请流程 Application

主管审批通过后，员工需在 IT 服务台提交工单登记远程日，模板如下：

```text
主题：远程办公登记 Remote Work Registration
姓名 / 工号：
远程日期：2026-__-__ 至 2026-__-__
代理人（当天紧急联系人）：
是否需 VPN 与内网访问：
```

## 五、其他 Miscellaneous

远程期间的考勤以企业微信在线状态与工单登记为准；未登记而远程办公的，按缺卡处理，
参照《假勤管理与加班调休制度》第二章 2.1 的迟到与旷工认定标准执行。
"""


def build_md():
    with open(MD_OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(MD_TEXT)
    return MD_OUT


if __name__ == "__main__":
    print("wrote", build_docx())
    print("wrote", build_md())
