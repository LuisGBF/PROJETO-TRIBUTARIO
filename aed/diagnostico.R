# Verificação de qualidade dos dados brutos que foram gerados pelo simulador

library(tidyverse)
library(janitor)
library(skimr)


# Leitura dos dados

arquivos <- list.files("dados/brutos", pattern = "\\.csv$", full.names = TRUE)
length(arquivos)

brutos <- read_csv(arquivos,
                   col_types = cols(.default = col_character()),
                   id = "arquivo_origem")
                   
dim(brutos)

glimpse(brutos)
skim(brutos)

# Verificação de valores duplicados

sum(duplicated(brutos$id_lancamento))

brutos |>
  get_dupes(id_lancamento) |>
  select(id_lancamento, dupe_count, cnpj_basico, competencia) |>
  head()

unicos <- distinct(brutos, id_lancamento, .keep_all = TRUE)
nrow(unicos)


# Verificar se há valores ausentes

colSums(is.na(unicos))

# Verificar a escrita das categorias 
unicos |> tabyl(macro_setor) |> arrange(desc(n))
unicos |> tabyl(regime_atual)

# Verficiar os formatos dos valores da receita

sum(str_detect(unicos$receita_bruta_mensal, ","))

# Verificar se há datas com formato fora do padrão

sum(!str_detect(unicos$data_hora_geracao, "^\\d{4}-\\d{2}-\\d{2}T"))
unicos |>
  filter(!str_detect(data_hora_geracao, "^\\d{4}-\\d{2}-\\d{2}T")) |>
  distinct(data_hora_geracao) |>
  head(3)

# Verificar se há CNPJ fora do padrão

sum(!str_detect(unicos$cnpj_basico, "^\\d{8}$"))
unicos |>
  filter(!str_detect(cnpj_basico, "^\\d{8}$")) |>
  select(cnpj_basico) |>
  head(5)

# Verificar se há outliers, valores fora do padrão da receita

receita <- as.numeric(str_replace(unicos$receita_bruta_mensal, ",", "."))
summary(receita)

# Verificar se há receitas com valores impossíveis, zeradas ou com valores negativos

sum(receita <= 0)

# Regra do intervalo interquartil na escala original
q1 <- quantile(receita, 0.25)
q3 <- quantile(receita, 0.75)
limite <- q3 + 3 * (q3 - q1)
limite
sum(receita > limite)

# Mesma regra na escala logarítmica, só com as receitas positivas
log_receita <- log10(receita[receita > 0])
q1_log <- quantile(log_receita, 0.25)
q3_log <- quantile(log_receita, 0.75)
limite_log <- q3_log + 3 * (q3_log - q1_log)
10^limite_log
sum(log_receita > limite_log)