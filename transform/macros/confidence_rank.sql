{#
  Confidence as a number, so the weakest of several inputs can be taken with
  greatest(). Lower is better.

  A value that was itself derived reports its own inputs' confidence, because
  "derived" describes how it was produced, not how good its ingredients were.
#}
{% macro confidence_rank(alias) %}
    case coalesce({{ alias }}.inputs_confidence, {{ alias }}.confidence)
        when 'high' then 1
        when 'medium' then 2
        else 3
    end
{%- endmacro %}
