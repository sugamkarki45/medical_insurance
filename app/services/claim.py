# here this is not required as the logic has been moved to local_validator.py

# from typing import Dict
# from app.model import ClaimInput, ClaimResponse, Item,  ClaimableItem
# import json

# class ClaimProcessor:
#     def __init__(self, rules_path: str = 'data/claimable_medicines.json'):
#         with open(rules_path, 'r') as f:
#             self.rules = json.load(f)
    
#     def calculate_claim(self, input: ClaimInput, optional_remaining_balance: float = None) -> ClaimResponse:
#         # Initialize
#         total_billed = input.total_billed
#         total_claimable = 0.0
#         deductible = self.rules['claim_limits']['deductible']
#         co_payment_pct = self.rules['claim_limits']['co_payment'] / 100
#         annual_limit = self.rules['claim_limits']['annual']
#         remaining = optional_remaining_balance or (annual_limit - input.family_annual_claim)  # Fallback to estimate
#         claimable_items = []
#         errors = []

#         # Process each item
#         for item in input.items:
#             rule = self._find_matching_rule(item)
#             if not rule:
#                 errors.append(f"No rule for item {item.name}")
#                 claimable_items.append(ClaimableItem(original_item=item, claimable_amount=0.0, reason='Invalid: No matching rule', applied_rules=[]))
#                 continue
            
#             # Validate (e.g., check formulary - assume a function or JSON list)
#             if not self._is_valid_per_rule(item, rule):
#                 errors.append(f"Item {item.name} fails validation: {rule.get('validation')}")
#                 claimable_items.append(ClaimableItem(original_item=item, claimable_amount=0.0, reason='Invalid', applied_rules=[rule['category']]))
#                 continue
            
#             # Calculate claimable
#             max_amt = rule.get('max_amount', float('inf'))
#             item_claimable = min(item.billed_amount * item.quantity, max_amt)
#             discount = rule.get('discount', 0) / 100
#             item_claimable *= (1 - discount)  # Apply discount if any
            
#             total_claimable += item_claimable
#             claimable_items.append(ClaimableItem(original_item=item, claimable_amount=item_claimable, reason='Approved', applied_rules=[rule['category']]))
        
#         # Apply global deductions
#         deductible_applied = min(deductible, total_claimable)
#         total_claimable -= deductible_applied
#         co_payment = total_claimable * co_payment_pct
#         total_claimable -= co_payment
        
#         # Check against remaining
#         if total_claimable > remaining:
#             total_claimable = remaining
#             errors.append("Claim exceeds remaining balance; capped")
        
#         remaining_after = remaining - total_claimable
        
#         return ClaimResponse(
#             claim_code=input.claim_code,
#             total_billed=total_billed,
#             total_claimable=total_claimable,
#             deductible_applied=deductible_applied,
#             co_payment=co_payment,
#             remaining_after_claim=remaining_after,
#             items=claimable_items,
#             validation_errors=errors,
#             is_submittable=len(errors) == 0
#         )
    
#     def _find_matching_rule(self, item: Item) -> Dict:
#         # Search rules by category/type (extend for lab_rules, etc.)
#         for r in self.rules.get('medicine_rules', []) + self.rules.get('lab_rules', []):  # Concat if multiple sections
#             if r['category'] == item.category:
#                 return r
#         return None
    
#     def _is_valid_per_rule(self, item: Item, rule: Dict) -> bool:
#         # Implement custom validation, e.g., check code against JSON formulary list
#         return True  # Placeholder; add logic like if item.code in rule.get('allowed_codes', [])

# # Usage in API endpoint (e.g., FastAPI)
# from fastapi import FastAPI, Body
# app = FastAPI()
# processor = ClaimProcessor()

# @app.post("/api/insurance/calculate_claim")
# def calculate_claim(input: ClaimInput = Body(...), remaining_balance: float = None):
#     return processor.calculate_claim(input, remaining_balance)