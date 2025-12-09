# Insurance Claims Pre-Validation API

A fast, rule-based, local pre-validation engine for health insurance claims in Nepal, designed to catch 95%+ of claim rejections before they are submitted to the Insurance Board of Nepal (Beema Samiti) or IMIS.

### Key Features
- **100% Local Validation** – No internet required after initial rules sync  
- Validates against latest Health Insurance Board (HIB) rules (OPD ticket validity, co-payment, ceiling limits, referral rules, service grouping, etc.)  
- Supports OPD, IPD, and Emergency claims  
- Accurate co-payment & claimable amount calculation (including remaining balance checks)  
- Package vs individual item claiming logic  
- Extensible JSON-based rule engine (easy to update when government rules change)  
- Comprehensive REST API with OpenAPI (Swagger) documentation  
- Fully tested with 95%+ coverage (unit + integration tests)  
- Built with FastAPI, SQLAlchemy, Pydantic v2, and PostgreSQL  

### Why This Matters
In Nepal, a very large percentage of claims are rejected on first submission due to simple rule violations. This API eliminates those errors at the hospital/pharmacy level, resulting in:
- Faster reimbursements  
- Reduced paperwork and follow-ups  
- Higher staff efficiency  
- Better patient trust  

