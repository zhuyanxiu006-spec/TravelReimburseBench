# Frozen primary action codebook

This table is derived directly from `gt/cases.jsonl`. Counts are primary annotations; a case may contain additional evidence facts. The release does not infer extra codes from model outputs.

| Code | Gold action | Cases | Description from frozen annotation |
|---|---|---:|---|
| `D_HOTEL_INVOICE_MISSING_OVERNIGHT` | defer | 8 | 车票证明存在过夜区间，但当前材料未提供酒店发票。 |
| `D_HOTEL_KEY_FIELD_UNREADABLE` | defer | 26 | 酒店发票的单价、金额、税额与价税合计均不可读，实付住宿费无法确定；限额表只给出每人每晚上限，不能反推实付金额，住宿可报金额与最终总额无法核定。 |
| `D_INCOMPLETE_ONE_WAY_CHAIN` | defer | 6 | 现有交通票据只能形成未闭合的单程行程，无法确定完整差旅区间。 |
| `D_MISSING_TICKET` | defer | 39 | 必要交通票据缺失，需补充票据或不完整行程说明及审批。 |
| `D_MULTI_CITY_PARTIAL_LODGING` | defer | 6 | 多城市过夜行程仅有部分城市的住宿证据。 |
| `D_MULTI_PERSON_LODGING_ATTRIBUTION_UNCLEAR` | defer | 6 | 多人住宿的入住人、人数或费用归属不唯一。 |
| `D_SUSPECTED_DUPLICATE_HOTEL_INVOICE` | defer | 17 | 酒店发票重叠或高度相似，需确认是否重复上传、拆票或分房。 |
| `D_SUSPECTED_DUPLICATE_TICKET` | defer | 36 | 存在重复或高度相似车票，但当前材料不足以证明已经重复报销。 |
| `D_TICKET_AMOUNT_UNREADABLE` | defer | 30 | 车票金额不可读，交通费和总额无法确定。 |
| `D_TICKET_PASSENGER_UNREADABLE` | defer | 6 | 车票乘车人不可读，无法确认票据归属和人员一致性。 |
| `P_COMPLETE_EVIDENCE` | process | 45 | 证据充分、规则明确，可自动完成核验与金额计算。 具体情形：正常。 |
| `P_HOTEL_LIMIT_REDUCTION` | process | 67 | 票据可构建清晰行程，住宿城市和日期可对应；住宿费用按报销规定计算。 |
| `P_SAME_DAY_RETURN_NO_LODGING` | process | 13 | 完整车票证明当天往返，不存在过夜区间；无酒店发票不阻断自动处理，住宿费为0。 |
| `P_SEASONAL_LODGING_POLICY` | process | 32 | 证据充分、规则明确，可自动完成核验与金额计算。 具体情形：住宿淡旺季合规。 |
| `P_SPECIAL_MEAL_POLICY` | process | 23 | 证据充分、规则明确，可自动完成核验与金额计算。 具体情形：伙食特殊地区。 |
| `R_DISJOINT_TICKET_HOTEL_GROUPS` | reject | 12 | 酒店入住人员与车票人员为两组完全不相交的人员，明显不属于同一批差旅。 |
| `R_HOTEL_CITY_DIRECT_CONFLICT` | reject | 37 | 酒店城市与完整车票重建出的全部目的城市直接冲突。 |
| `R_HOTEL_TIME_DIRECT_CONFLICT` | reject | 49 | 酒店住宿日期全部位于完整车票行程区间之外。 |
| `R_MUTUALLY_EXCLUSIVE_TICKETS` | reject | 21 | 同一人员在相同日期和时间持有两张不同路线车票，无法同时成立。 |
| `R_SINGLE_PERSON_TICKET_NAME_CONFLICT` | reject | 15 | S1/S2单人行程的可读车票出现不同乘车人，构成明确身份冲突。 |
| `R_TICKET_DATE_INVERSION` | reject | 46 | 同一人员的可读车票行程段日期顺序倒置，现有票据直接构成不可能行程。 |
