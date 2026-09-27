{#
  Every published line is counted exactly once by confidence. If these stop adding
  up, either a new confidence level was introduced without the report learning
  about it, or a filter is double counting, and every trust label becomes suspect.
#}

select
    ticker,
    statement,
    period_end,
    lines_present,
    high_lines + medium_lines + low_lines + derived_lines as counted_lines
from {{ ref('mart_confidence_report') }}
where high_lines + medium_lines + low_lines + derived_lines != lines_present
