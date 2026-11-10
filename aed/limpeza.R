# Limpeza e tratamento dos dados brutos gerados pelo simulador da VM
# Entrada -> dados/brutos/*.csv (os dados são preservados e não são alterados diretamente)
# Saída -> dados/tratados/movimentacao_tratada.csv
#          dados/tratados/registros_descartados.csv

library(tidyverse)

# Leitura dos dados

arquivos <- list.files("dados/brutos", pattern = "\\.csv$", full.names = TRUE)
brutos <- read_csv(arquivos,
                   col_types = cols(.default = col_character()),
                   id = "arquivo_origem"
                   )

# Removendo valores duplicados

etapa1 <- brutos |>
  distinct(id_lancamento, .keep_all = TRUE) |>
  mutate(arquivo_origem = basename(arquivo_origem))

# Padronizando os formatos

colunas_valor <- c("receita_bruta_mensal", "folha_salarios_mensal", "custo_mercadoria_vendida", "despesas_operacionais", "compras_com_credito")

etapa2 <- etapa1 |>
  mutate(
    # Tira a pontuação do CNPJ e completa com zeros à esquerda até chegar em 8 números
    cnpj_basico = str_pad(str_remove_all(cnpj_basico, "\\D"),
                          width = 8, side = "left", pad = "0"),
    
    # Unificando a escrita dos nomes dos setores
    macro_setor = case_when(
      str_starts(str_to_lower(macro_setor), "com")  ~ "Comércio",
      str_starts(str_to_lower(macro_setor), "serv") ~ "Serviços",
      str_starts(str_to_lower(macro_setor), "ind")  ~ "Indústria"
    ),
    
    # Troca a vírgula por ponto e converte para número dos valores
    across(all_of(colunas_valor), \(x) as.numeric(str_replace(x, ",", "."))),
    
    # Aceita os dois formatos para data e hora
    data_hora_geracao = parse_date_time(data_hora_geracao,
                                        orders = c("Ymd HMS", "dmY HM"))
  )

# Identificando e separando os outliers 

log_receita <- log10(etapa2$receita_bruta_mensal[etapa2$receita_bruta_mensal > 0])
q1_log <- quantile(log_receita, 0.25)
q3_log <- quantile(log_receita, 0.75)
limite_receita <- 10^(q3_log + 3 * (q3_log - q1_log))

etapa3 <- etapa2 |>
  mutate(motivo_descarte = case_when(
    receita_bruta_mensal <= 0             ~ "receita zero ou negativa",
    receita_bruta_mensal > limite_receita ~ "receita discrepante",
    .default = NA_character_
  ))

descartados <- etapa3 |> filter(!is.na(motivo_descarte))
validos     <- etapa3 |> filter(is.na(motivo_descarte)) |> select(-motivo_descarte)

# Preenchendo os valores ausentes
# Utiliza a mediana de cada valor em relação à receita, por setor

proporcoes <- validos |>
  group_by(macro_setor) |>
  summarise(
    p_folha    = median(folha_salarios_mensal    / receita_bruta_mensal, na.rm = TRUE),
    p_custo    = median(custo_mercadoria_vendida / receita_bruta_mensal, na.rm = TRUE),
    p_despesas = median(despesas_operacionais    / receita_bruta_mensal, na.rm = TRUE)
  )
proporcoes

tratados <- validos |>
  left_join(proporcoes, by = "macro_setor") |>
  mutate(
    folha_imputada     = is.na(folha_salarios_mensal),
    custo_imputado     = is.na(custo_mercadoria_vendida),
    despesas_imputadas = is.na(despesas_operacionais),
    folha_salarios_mensal    = coalesce(folha_salarios_mensal,
                                        round(receita_bruta_mensal * p_folha, 2)),
    custo_mercadoria_vendida = coalesce(custo_mercadoria_vendida,
                                        round(receita_bruta_mensal * p_custo, 2)),
    despesas_operacionais    = coalesce(despesas_operacionais,
                                        round(receita_bruta_mensal * p_despesas, 2))
  ) |>
  select(-starts_with("p_"))

# Verificando a qualidade dos dados

verificacoes <- c(
  "sem duplicatas"       = !any(duplicated(tratados$id_lancamento)),
  "CNPJ com 8 dígitos"   = all(str_detect(tratados$cnpj_basico, "^\\d{8}$")),
  "setor padronizado"    = all(tratados$macro_setor %in% c("Comércio", "Serviços", "Indústria")),
  "sem valores ausentes" = !anyNA(tratados),
  "receita positiva"     = all(tratados$receita_bruta_mensal > 0)
)
verificacoes
stopifnot(all(verificacoes))

# Resumo do tratamento

tibble(
  etapa = c("Registros brutos", "Após remover duplicatas",
            "Descartados (receita negativa ou discrepante)", "Registros tratados",
            "Registros com algum valor preenchido"),
  registros = c(nrow(brutos), nrow(etapa1), nrow(descartados), nrow(tratados),
                sum(tratados$folha_imputada | tratados$custo_imputado |
                      tratados$despesas_imputadas))
)
descartados |> count(motivo_descarte)

# Salvando os resultados

dir.create("dados/tratados", showWarnings = FALSE)

tratados |>
  mutate(data_hora_geracao = format(data_hora_geracao, "%Y-%m-%d %H:%M:%S")) |>
  write_csv("dados/tratados/movimentacao_tratada.csv")

descartados |>
  mutate(data_hora_geracao = format(data_hora_geracao, "%Y-%m-%d %H:%M:%S")) |>
  write_csv("dados/tratados/registros_descartados.csv")

list.files("dados/tratados")

