

**Endpoint:** `GET /items`
### header
``` json
{
  "X-API-Key":"API key" 
}
```
### Response Example

```json
[
  "count": 1,  // total count of all the items in HIB catalogue
  "medicines": [
    {
      "code": "MED001IVFES",
      "name": "10% DEXTROSE 500/540ML GLASS BTL.",
      "type": "medicine",
      "sub_type": null,
      "rate_npr": 70,
      "capping": {
        "max_days": null,
        "max_per_visit": 10
      },
      "claimable": true
    },
    {
      "code": "MED001IVFES",
      "name": "10% DEXTROSE 500/540ML GLASS BTL.",
      "type": "medicine",
      "sub_type": null,
      "rate_npr": 70,
      "capping": {
        "max_days": null,
        "max_per_visit": 10
      },
      "claimable": true
    }]
]
```

---
