
**Endpoint:** `POST /patient/full-info`

### Header Requirement
```json
{
  "X-API-Key":"API key" 
}

```
### Request Body
``` json
{
  "patient_identifier": "string",
  "username": "string",
  "password": "string"
}
```

### Response Example

```json

{
  "patient_code": "740500036",      
  "uuid": "C335B6A2-738C-4373-AFF4-DAD1B8B09645",  
  "name": "Test Bima ",              
  "birthDate": "2016-04-07",         
  "gender": "Male",                  
  "copayment": "0.10",                
  "allowed_money": "25520.00",       
  "used_money": "0.00",             
  "category": "medical",             
  "policy_id": "HIB-3500",          
  "policy_expiry": "2026-11-16",      
  "imis": {
    "resourceType": "Bundle",         
    "entry": [
      {
        "fullUrl": "http://localhost/api/api_fhir/Patient/C335B6A2-738C-4373-AFF4-DAD1B8B09645", 
        "resource": {
          "resourceType": "Patient",   
          "address": [
            {
              "text": "0.0 0.0",       
              "type": "both",         
              "use": "home"          
            }
          ],
          "birthDate": "2016-04-07",  
          "extension": [
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960069653/FHIR+extension+isHead",
              "valueBoolean": true    
            },
            {
              "url": "https://openimis.atlassian.net/wiki/spaces/OP/pages/960331779/FHIR+extension+registrationDate",
              "valueString": "2024-07-31 15:52:57.760000" 
            },
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,    
              "valueString": "NormalHibScheme " 
            }
          ],
          "gender": "Male",             
          "id": "C335B6A2-738C-4373-AFF4-DAD1B8B09645", 
          "identifier": [
            {
              "type": { "coding": [{"code": "ACSN"}]},
              "use": "usual",
              "value": "C335B6A2-738C-4373-AFF4-DAD1B8B09645" 
            },
            {
              "type": { "coding": [{"code": "SB"}]},
              "use": "usual",
              "value": "740500036"    
            }
          ],
          "name": [
            {
              "family": "Number",      
              "given": ["Test Bima "], 
              "use": "usual"
            }
          ],
          "telecom": [
            {
              "system": "phone",        
              "use": "home",
              "value": "9871717177"    
            }
          ]
        }
      }
    ],
    "total": 1                        
  },
  "eligibility": {
    "success": true,                  
    "data": {
      "resourceType": "EligibilityResponse", 
      "insurance": [
        {
          "benefitBalance": [
            {
              "category": { "text": "medical" }, 
              "financial": [
                {
                  "allowedMoney": {"value": 25520}, 
                  "usedMoney": {"value": 0}     
                }
              ]
            }
          ],
          "contract": {"reference": "Contract/HIB-3500/2026-11-16 00:00:00"}, 
          "extension": [
            {
              "url": "https://hib.gov.np/fhir/FHIE+extension+Copayment",
              "valueDecimal": 0.1,
              "valueString": "NormalHibScheme "  
            }
          ]
        }
      ]
    }
  }
}

```

---

