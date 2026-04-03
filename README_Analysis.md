# APT Attack Analysis on Linux Systems

This project analyzes the Linux APT (Advanced Persistent Threat) attack dataset to identify attack patterns, sequences, and MITRE ATT&CK techniques used by attackers.

## Overview

The analysis processes security event logs from Linux systems that have been compromised by APT actors, extracting and visualizing the attack sequences using MITRE ATT&CK framework mapping.

## Dataset

- **Source**: `Linux-APT-Dataset-2024/combine.csv`
- **Total Events**: 91,133 security events
- **Time Range**: October 1-5, 2023
- **Compromised Hosts**: 3 agents (ubuntu, machine-1, Machine-1-New)

## Analysis Steps

1. **Data Preprocessing**
   - Loaded and cleaned the CSV dataset
   - Parsed custom timestamp format
   - Extracted relevant security fields

2. **Field Extraction**
   - `_source.@timestamp` - Event timestamp
   - `_source.agent.id` - Host identifier
   - `_source.full_log` - Complete log entry
   - `_source.rule.mitre_tactics` - MITRE ATT&CK tactics
   - `_source.rule.mitre_techniques` - MITRE ATT&CK techniques
   - `_source.rule.description` - Event description

3. **Filtering**
   - Filtered to 348 events with valid MITRE ATT&CK data
   - Removed invalid/noisy MITRE identifiers
   - Validated tactic (TA) and technique (T) codes

4. **Temporal Analysis**
   - Sorted events chronologically
   - Grouped events by compromised host
   - Built timeline of attack progression

5. **Graph Construction**
   - Created directed graph with 142 nodes (tactic-technique pairs)
   - Generated 422 edges (temporal transitions)
   - Weighted edges by transition frequency

## Key Findings

### Attack Statistics
- **Events with MITRE Data**: 348 (78.52% of filtered data)
- **Unique MITRE Tactics**: 13
- **Unique MITRE Techniques**: 72
- **Attack Duration**: ~5 days
- **Graph Nodes**: 142 unique tactic-technique combinations
- **Graph Edges**: 422 temporal transitions

### Top MITRE Tactics
1. **TA0005** - Defense Evasion (most common)
2. **TA0008** - Lateral Movement
3. **TA0007** - Discovery
4. **TA0006** - Credential Access
5. **TA0011** - Command and Control

### Top MITRE Techniques
1. **T1562** - Impair Defenses
2. **T1543** - Create or Modify System Process
3. **T1543.002** - Systemd Service
4. **T1203** - Exploitation for Client Execution
5. **T1070** - Indicator Removal

### Common Attack Transitions
Most frequent attack progressions:
1. T1543 → T1543.002 (23 times)
2. T1203 → T1210 (20 times)
3. T1562.004 → T1562 (20 times)
4. T1562 → T1562.004 (20 times)
5. T1210 → T1543 (16 times)

### Per-Host Attack Summary

**Agent 0 (ubuntu)**
- Events: 173
- Duration: 3 days, 16:32:13
- Tactics: 16 unique
- Techniques: 52 unique

**Agent 1 (machine-1)**
- Events: 174
- Duration: 1 day, 00:43:59
- Tactics: 16 unique
- Techniques: 52 unique

**Machine-1-New**
- Events: 1
- Limited data available

## Generated Outputs

### CSV Files
1. **apt_attack_events_processed.csv** - Expanded event data with parsed MITRE info
2. **apt_mitre_data_sorted.csv** - Chronologically sorted MITRE events
3. **attack_sequence_edges.csv** - Graph edge list with transition weights

### Visualizations
1. **attack_sequence_graph.png** - Static graph showing attack progression
   - Nodes: MITRE tactic-technique pairs
   - Edges: Temporal transitions between techniques
   - Edge weights: Transition frequency

2. **mitre_distribution.png** - Bar charts showing:
   - Top 15 MITRE ATT&CK tactics by frequency
   - Top 15 MITRE ATT&CK techniques by frequency

3. **attack_timeline.png** - Line chart showing attack events over time

4. **attack_sequence_interactive.html** - Interactive graph (open in browser)
   - Explore nodes and connections dynamically
   - Zoom and pan capabilities

### Summary Files
- **analysis_summary.json** - Complete analysis statistics in JSON format

## How to Use

### Running the Analysis
1. Open `test_dataset.ipynb` in Jupyter or VS Code
2. Run all cells sequentially
3. View generated visualizations and exported files

### Viewing Results
- **Static Images**: Open PNG files directly
- **Interactive Graph**: Open `attack_sequence_interactive.html` in web browser
- **Data Files**: Open CSV files in Excel or any spreadsheet software
- **Summary**: View `analysis_summary.json` for quick statistics

## Requirements

```
pandas
numpy
matplotlib
seaborn
networkx
plotly (optional, for interactive graphs)
```

## Insights and Recommendations

### Attack Pattern Observations
1. **Defense Evasion (TA0005)** is the most common tactic, indicating attackers focused on avoiding detection
2. **T1562 (Impair Defenses)** suggests attempts to disable security controls
3. **System persistence** through T1543 (Create/Modify System Process) is prevalent
4. **Lateral movement** (TA0008) indicates multi-host compromise attempts

### Security Recommendations
1. **Strengthen monitoring** for defense evasion techniques
2. **Protect system services** from unauthorized modification
3. **Implement robust endpoint detection** for indicator removal attempts
4. **Monitor lateral movement** patterns across network
5. **Harden systemd services** against unauthorized changes

## MITRE ATT&CK Mapping

This analysis uses the MITRE ATT&CK framework to map observed security events to known adversary tactics and techniques. Each event is tagged with:
- **Tactics**: High-level adversary goals (e.g., Defense Evasion)
- **Techniques**: Specific methods used to achieve tactics (e.g., T1562 - Impair Defenses)

For more information on MITRE ATT&CK: https://attack.mitre.org/

## Notes

- Some events lacked timestamp data and were excluded from temporal analysis
- MITRE data underwent cleaning to remove invalid identifiers
- Graph layout uses spring layout algorithm for optimal node positioning
- Edge weights indicate frequency of tactic-technique transitions

## Future Enhancements

1. Add machine learning for attack pattern classification
2. Implement anomaly detection for unusual transitions
3. Create kill chain visualization
4. Add predictive analysis for next likely attack steps
5. Integrate with threat intelligence feeds

---

**Analysis Date**: November 16, 2025  
**Dataset Period**: October 1-5, 2023  
**Tool**: Jupyter Notebook with Python data science stack
