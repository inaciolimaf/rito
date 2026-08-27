"""Observabilidade do Rito (spec 097): log correlacionado, trace e métricas.

O resto do sistema importa daqui — `app.core.observability.metrics.record_*` para
métrica de domínio, `context` para ler quem é o tenant da ação corrente. Ninguém
importa `prometheus_client` nem `opentelemetry` fora deste pacote (CLAUDE.md §5, DIP).
"""
