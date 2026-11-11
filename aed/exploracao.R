# Análise exploratória dos dados tratados
# Entrada: dados/tratados/movimentacao_tratada.csv

library(tidyverse)
library(janitor)

# Leitura dos dados

tratados <- read_csv("dados/tratados/movimentacao_tratada.csv",
                     col_types = cols(cnpj_basico = col_character(),
                                      cnae_fiscal_principal =col_character(),
                                      competencia = col_character())
                     )
glimpse(tratados)

# Novas váriaveis

explorar <- tratados |>
  mutate(
    receita_anual_estimada = receita_bruta_mensal * 12,
    proporcao_folha = folha_salarios_mensal / receita_bruta_mensal,
    margem_estimada = (receita_bruta_mensal - folha_salarios_mensal - 
                         custo_mercadoria_vendida - despesas_operacionais) /
      receita_bruta_mensal,
    faixa_receita = cut(receita_anual_estimada,
                        breaks = c(0, 360000, 4800000, 78000000, Inf),
                        labels = c("até 360 mil", "360 mil a 4,8 mi",
                                   "4,8 mi a 78 mi", "acima de 78 mi")
                        )
  )

# Medidas descritivas 

colunas_valor <- c("receita_bruta_mensal", "folha_salarios_mensal",
                   "custo_mercadoria_vendida", "despesas_operacionais",
                   "compras_com_credito"
                   )

medidas <- explorar |>
  pivot_longer(all_of(colunas_valor), names_to = "variavel", values_to = "valor") |>
  group_by(variavel) |>
  summarise(
    media     = mean(valor),
    mediana   = median(valor),
    variancia = var(valor),
    desvio    = sd(valor),
    coef_var  = sd(valor) / mean(valor),
    minimo    = min(valor),
    q1        = quantile(valor, 0.25),
    q3        = quantile(valor, 0.75),
    maximo    = max(valor)
  ) |>
  mutate(across(where(is.numeric), \(x) round(x, 2)))
print(as.data.frame(medidas))

# Frequencias

explorar |> tabyl(regime_atual) |> adorn_pct_formatting()
explorar |> tabyl(macro_setor) |> adorn_pct_formatting()

explorar |>
  tabyl(macro_setor, regime_atual) |>
  adorn_percentages("row") |>
  adorn_pct_formatting() |>
  adorn_ns()

explorar |> tabyl(faixa_receita, regime_atual)

# Agrupamentos

explorar |>
  group_by(regime_atual) |>
  summarise(
    registros        = n(),
    receita_mediana  = median(receita_bruta_mensal),
    folha_sobre_rec  = median(proporcao_folha),
    margem_mediana   = median(margem_estimada)
  )

explorar |>
  group_by(macro_setor) |>
  summarise(
    registros        = n(),
    receita_mediana  = median(receita_bruta_mensal),
    folha_sobre_rec  = median(proporcao_folha),
    margem_mediana   = median(margem_estimada)
  )

explorar |>
  group_by(competencia) |>
  summarise(
    registros       = n(),
    receita_mediana = median(receita_bruta_mensal),
    receita_total   = sum(receita_bruta_mensal)
  )

explorar |>
  select(all_of(colunas_valor)) |>
  cor(method = "spearman") |>
  round(2)

# Preparação dos gráficos

cores_setor <- c("Comércio" = "#2a78d6", "Indústria" = "#eb6834", "Serviços" = "#1baf7a")
reais <- scales::label_number(prefix = "R$ ", big.mark = ".", decimal.mark = ",",
                              scale_cut = c(0, " mil" = 1e3, " mi" = 1e6))
theme_set(theme_minimal(base_size = 12))
dir.create("aed/graficos", showWarnings = FALSE)

# Distribuição da receita

g1 <- ggplot(explorar, aes(x = receita_bruta_mensal)) +
  geom_histogram(bins = 40, fill = "#2a78d6", color = "white") +
  scale_x_log10(labels = reais) +
  labs(title = "Distribuição da receita bruta mensal",
       subtitle = "Eixo horizontal em escala logarítmica",
       x = "Receita bruta mensal", y = "Número de registros")
g1
ggsave("aed/graficos/01_distribuicao_receita.png", g1, width = 8, height = 5, dpi = 150)

# Receita por regime

g2 <- ggplot(explorar, aes(x = regime_atual, y = receita_bruta_mensal)) +
  geom_boxplot(fill = "#b7d3f6", outlier.alpha = 0.3) +
  scale_y_log10(labels = reais) +
  labs(title = "Receita bruta mensal por regime tributário",
       subtitle = "Eixo vertical em escala logarítmica",
       x = NULL, y = "Receita bruta mensal")
g2
ggsave("aed/graficos/02_receita_por_regime.png", g2, width = 8, height = 5, dpi = 150)

# Folha em relação à receita

g3 <- ggplot(explorar, aes(x = receita_bruta_mensal, y = folha_salarios_mensal,
                           color = macro_setor)) +
  geom_point(alpha = 0.4, size = 1.5) +
  scale_x_log10(labels = reais) +
  scale_y_log10(labels = reais) +
  scale_color_manual(values = cores_setor) +
  labs(title = "Folha de salários em relação à receita",
       subtitle = "Os dois eixos em escala logarítmica",
       x = "Receita bruta mensal", y = "Folha de salários mensal", color = "Setor")
g3
ggsave("aed/graficos/03_folha_receita.png", g3, width = 8, height = 5, dpi = 150)

# Margem estimada por setor

presuncao <- tibble(macro_setor = c("Comércio", "Indústria", "Serviços"),
                    margem = c(0.08, 0.08, 0.32))

g4 <- ggplot(explorar, aes(x = macro_setor, y = margem_estimada)) +
  geom_boxplot(aes(fill = macro_setor), outlier.alpha = 0.3, show.legend = FALSE) +
  geom_point(data = presuncao, aes(y = margem), shape = 23, size = 4, fill = "black") +
  scale_fill_manual(values = cores_setor) +
  scale_y_continuous(labels = scales::label_percent(decimal.mark = ",")) +
  labs(title = "Margem estimada por setor",
       subtitle = "Losango preto: lucro presumido pelo Lucro Presumido para o IRPJ",
       x = NULL, y = "Margem estimada (% da receita)")
g4
ggsave("aed/graficos/04_margem_por_setor.png", g4, width = 8, height = 5, dpi = 150)

list.files("aed/graficos")

