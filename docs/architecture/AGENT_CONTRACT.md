# RackMarshal Agent Contract

Status: **FROZEN CONTRACT BASELINE**
Date: 2026-09-29

## Contract

An agent interacting with RackMarshal MUST distinguish operational evidence from interpretation.

### An agent MAY

- read authorized RackMarshal state;
- summarize observations, events, incidents, and recovery history;
- correlate recorded changes;
- request additional read-only evidence;
- produce advisory explanations and hypotheses;
- recommend checks or remediations;
- request an action only when that capability exists and policy permits it.

### An agent MUST NOT

- declare infrastructure healthy without RackMarshal evidence;
- close or resolve an incident merely because an action completed;
- rewrite observations, events, or evidence;
- treat model confidence as operational proof;
- bypass policy, approval, or capability boundaries;
- access the private RackMarshal database directly through the public agent interface.

### Recovery rule

An agent may say: **"The requested action completed."**

Only RackMarshal may authoritatively say: **"Recovery was observed and verified."**
