# แผนปรับ workflow ให้ตอบ XHARD ถูก (20 ข้อ)

> อิงจากการอ่านคำถาม XHARD ทั้ง 20 + ground_truth + method + trap ใน `crosscheck.csv`
> เป้าหมาย: ยกคะแนน XHARD โดยแก้ที่ "ต้นเหตุเชิง workflow/tool" ไม่ใช่แก้คำตอบทีละข้อ

## 1. สถานะปัจจุบัน (auto_score เป็นไกด์ — คำตัดสินจริงต้องดู GT)
9/20 = REVIEW/ผิด, 11/20 = PASS (บาง PASS ยังตกรายละเอียด)

| ข้อ | auto | ปัญหาหลัก | bucket |
|---|---|---|---|
| XHARD-004 | 7/15 🔴 | baseline 858k≠865k (LLM คิดเลขผิด) + พลาด renovation component | A,B |
| XHARD-005 | 5/11 🔴 | PKT loss 106.9M ผิด ~10× → combined เพี้ยน | A |
| XHARD-006 | 2/6 🔴 | ได้ 0 หมด (dependency พัง + ใช้ ceiling ผิดเวลา) | B,C |
| XHARD-001 | 3/6 | discount cost / net revenue (cohort) ขาด/ผิด, ROI | A,B |
| XHARD-007 | 4/8 | taxonomy count/THB per category | A,B |
| XHARD-009 | 9/16 | rate %, HDY trap, baseline vs observed | A,E |
| XHARD-018 | 2/7 | foregone revenue ถูก แต่ตกเดือน/5.2×/85% | A,completeness |
| XHARD-015 | 4/6 | นับ chat_line_oa threads ไม่ครบ (cross-modal) | D |
| XHARD-019 | 5/7 | ROI LTV — จัดการ data-limitation ได้ แต่ตัวเลข cost | A |
| XHARD-002/003/008/010/011/012/013/014/016/017/020 | PASS | ส่วนใหญ่โอเค (บางข้อตกรายละเอียดเล็ก) | — |

## 2. Root-cause buckets → ปริมาณข้อที่กระทบ
- **A. LLM คิดเลขหลายสเต็ปเอง** (synth คูณ/หาร/% ในหัว) → 001,004,005,007,009,011,018,019 **(ใหญ่สุด)**
- **B. subtask มี dependency** (หา X → คิดบน X) แต่ planner แตกเป็น parallel → 006,009,011,017,018,010
- **C. bitemporal as-of per-row** (ceiling/contract ณ business_event_date ไม่ใช่ query date) → 006,002,008,016
- **D. doc retrieval/นับ/cross-modal** (นับ thread, narrative + table) → 015,008,003,014 (+ HARD-018/001 นอก XHARD)
- **E. anti-shortcut trap** (ระบุในโจทย์เอง: 'CONTAINS not =', 'all-time', 'msrp not KB', 'HDY ไม่ใช่ branch') → 006,009,011,012,016,017,018

## 3. งานแก้ (เรียงตาม leverage) — แต่ละ fix โยงข้อที่แก้ได้

### Fix #1 — คิดเลขใน SQL ไม่ใช่ในหัว synth ⭐ (แก้ bucket A = มากสุด)
**ทำไม:** XHARD-004 เขียนสูตรถูก ("ควรได้ 864,572") แต่พิมพ์ 858,106; XHARD-005 คูณวันผิด 10×. LLM พลาด arithmetic หลายสเต็ป — SQL ไม่พลาด
**แก้:**
- `prompts/sql.md`: เพิ่มกฎ *"ถ้า subtask ขอค่าที่ต้องคำนวณ (baseline ต่อวัน, ratio, %, lift, ROI, foregone, lost-revenue) ให้ทำให้จบใน SQL เดียว (CTE) แล้ว SELECT ค่า scalar สุดท้าย — อย่าคืน component ดิบให้ผู้อื่นคูณ/หารต่อ"*
- `prompts/synth.md`: ปรับจาก *"ARITHMETIC: COMPUTE it yourself"* → *"ถ้า finding มีตัวเลขที่คำนวณมาแล้วให้ใช้ตามนั้น; ทำเองได้เฉพาะบวกง่าย ๆ ถ้าต้องคูณ/หาร/% ที่ซับซ้อน ให้ถือว่าเป็นงานของ SQL"*
- ไฟล์: `fahmai/agents/prompts/sql.md`, `synth.md`

### Fix #2 — Planner: เก็บ "หา X → คิดบน X" เป็น subtask เดียว + รองรับ dependency ⭐ (แก้ bucket B)
**ทำไม:** XHARD-006 ระบุเองว่า "subtask 2 ไปคิดของ EMP-L3-00005 แทน 00010" — planner แตก find/compute เป็น 2 parallel ที่มองกันไม่เห็น
**แก้ (เลือกทางใดทางหนึ่ง):**
- *เบา (แนะนำเริ่มก่อน):* `prompts/planner.md` เพิ่มกฎเข้ม + ตัวอย่าง: *"ถ้า part หลังต้องใช้ผลของ part หน้าเป็น filter/ขอบเขต (เช่น 'หา employee/branch/SKU/invoice แล้วคำนวณบนตัวนั้น') ต้องเป็น sql subtask เดียว ให้ SQL analyst iterate เอง ห้ามแตก"* — SQL ReAct agent ค้นหลายคิวรีต่อเนื่องได้อยู่แล้ว
- *หนัก (ถ้ายังไม่พอ):* เพิ่ม `needs:[id]` ใน planner schema + แก้ `graph.py` ให้ dependent subtask รันหลัง parent แล้วฉีดผล parent เข้า subquestion ลูก
- ไฟล์: `fahmai/agents/prompts/planner.md` (+ `graph.py` ถ้าทำแบบหนัก)

### Fix #3 — เสริม bitemporal as-of per-row (แก้ bucket C)
**ทำไม:** XHARD-006/016 ต้อง resolve ceiling ของ ladder ณ business_event_date แต่ละแถว (ไม่ใช่ ณ query date); XHARD-002 ต้อง resolve contract version active ต่อแถว
**แก้:** `prompts/sql.md` ย้ำ pattern + boundary: *"join dim_policy_version/dim_signing_authority_ladder ด้วย effective_date <= business_event_date AND (end_date IS NULL OR end_date > business_event_date) ต่อแถว; PM1 signing-authority cutover = 2025-02-15 (≠ PM-REFUND 2025-03-15)"* — และพิจารณาเพิ่มหมายเหตุ as-of join ลง `SCHEMA_CARD` (`fahmai/tools/schema_card.py`)

### Fix #4 — ออกแบบ doc-search tools ใหม่ (DB-backed filesystem-style) (แก้ bucket D)
**ทำไม:** XHARD-015 ต้องนับ Powercell X3 chats ใน chat_line_oa; HARD-018 ต้องนับ E3 แยก channel (chat_oa 150 / chat_works 4) — tool เดิมคืน 5 snippet ไม่บอก total → สรุปไม่ครบ
**แก้:** เปลี่ยน 3 tools เป็น filesystem-style (in-place, DB-backed) ตามที่ตกลง:
- `grep_docs(...) ` → คืน **total + offset** + snippet
- `list_docs(...)` → filter → ids + metadata + **total (+ breakdown ราย channel เมื่อไม่ระบุ channel)**
- `read_doc(doc_id, keyword, window)` → full text / window
- เขียน docstring ตาม good-practice (Args/Returns/Examples) + ลบ `search_docs_tool` (vector) ออกจาก `ALL_TOOLS`
- ไฟล์: `fahmai/agents/tools/query_docs.py`, `get_document.py`, `__init__.py`, `fahmai/tools/doc_tool.py` (query_docs/count_docs คืน total/breakdown), `prompts/doc.md`

### Fix #5 — กฎ "อ่าน/ทำตาม trap ในโจทย์" (แก้ bucket E)
**ทำไม:** หลายข้อมีกับดักเขียนในโจทย์เอง (CONTAINS≠'=', all-time≠2024, msrp from DIM_PRODUCT≠KB, HDY ไม่ใช่ branch_code)
**แก้:** `prompts/sql.md` + `synth.md` เพิ่ม: *"ถ้าโจทย์ระบุข้อจำกัด/คำเตือน (ใช้ X ไม่ใช่ Y, CONTAINS ไม่ใช่ =, all-time ไม่ใช่ปีเดียว, anchor ที่ตาราง master) ให้ทำตามตรงตัว อย่าใช้ทางลัด"*

### Fix #6 — Verify/critic node (กันพลาดทั้งชุด, ทำหลังสุด)
**ทำไม:** ดักเลขผิดก่อนตอบ (raw≥dedup, ผลรวม component ≈ total, ทุกเลขใน draft มีที่มาจาก finding)
**แก้:** เปิด node `verify` กลับมาใน `graph.py` (มี `verify.md` อยู่แล้ว) แต่ทำเป็น **data/arithmetic critic**: ถ้าเลขไม่ consistency → loop กลับ synth (หรือ re-dispatch SQL recompute) ครั้งเดียว
- ไฟล์: `fahmai/agents/graph.py`, `prompts/verify.md`

## 4. ลำดับลงมือ + การวัดผล
1. **Phase 1 (prompt-only, เสี่ยงต่ำ):** Fix #1 + #2(เบา) + #3 + #5 — แก้แค่ `.md` (sql/synth/planner) → ครอบ bucket A,B,C,E
2. **Phase 2:** Fix #4 (doc tools)
3. **Phase 3:** Fix #6 (verify node) + #2(หนัก) ถ้ายังพลาด

**วัดผล (ใช้ pattern เดิม):**
- ทำ XHARD eval set จาก `scripts/run_doc_eval.py` (เปลี่ยน `DOC_SET` → 20 XHARD ids) → รันผ่าน graph จริง → `scoring.score()` เทียบ GT
- เริ่มจาก 9 ข้อ REVIEW (โดยเฉพาะ 3 แดง: 004/005/006) + spot-check PASS ว่าไม่ regress
- regenerate `crosscheck.csv/html` ดู PASS เพิ่ม/ตัวเลขตรงขึ้น
- ⚠️ การ re-run ต้องมี OpenRouter API key + DB (Supabase) พร้อมใน `.env`

## 5. ไฟล์ที่จะแตะ (สรุป)
- prompts: `sql.md`, `synth.md`, `planner.md`, `doc.md`, `verify.md`
- graph: `fahmai/agents/graph.py` (dependency + verify node)
- tools: `fahmai/agents/tools/{query_docs,get_document,__init__}.py`, `fahmai/tools/doc_tool.py`, `schema_card.py`
- eval: `scripts/run_doc_eval.py` (→ XHARD set), `scripts/build_crosscheck.py` (มีแล้ว)
- ❌ ไม่แตะ: ingest/DB schema, ตารางข้อมูล, submission อื่น ๆ
