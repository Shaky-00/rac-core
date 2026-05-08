| plan_id | variant | rac_decision | server_call_issued | side_effect_exists | security_violation_materialized |
| --- | --- | --- | --- | --- | --- |
| attack_mixed_list_then_write_plan | FULL_RAC | BLOCK | false | false | false |
| attack_write_leak_plan | FULL_RAC | BLOCK | false | false | false |
| attack_mixed_list_then_write_plan | NO_RAC | NO_RAC_ALLOW | true | true | true |
| attack_write_leak_plan | NO_RAC | NO_RAC_ALLOW | true | true | true |

