# Roteiro de estudo para entrevista

Este é o projeto que conecta a sua experiência de engenharia com programação. Conte a história do processo real: quanto tempo um orçamento de reforma leva na construtora, e onde erra.

## 1. Explique o projeto em 1 minuto

"Orçar obra pequena é casar cada linha da lista do mestre de obras com um insumo da tabela SINAPI. Eu automatizei isso em Python. Primeiro importo a planilha da Caixa para o Postgres. Para cada linha da lista, extraio quantidade, unidade e material, busco os 5 insumos mais parecidos com full-text em português e trigramas, e escolho o certo. A extração e a escolha podem ser por regra ou pelo Claude. Duas regras: o preço sempre vem do banco, nunca da IA; e item em dúvida vai para revisão, fora do total. Tenho um conjunto de 30 linhas com gabarito e meço acertos, revisões e erros calados antes de mudar qualquer coisa."

## 2. Perguntas técnicas

**Por que a IA não dá o preço?**
Porque o modelo não sabe o preço do SINAPI do mês e, se não souber, pode inventar um número plausível. Preço errado num orçamento é prejuízo. A IA faz o que faz bem (entender "cp2" e "ferro 3/8") e o banco faz o resto. Mesmo a escolha é limitada aos candidatos que o banco devolveu: código fora da lista é descartado. → `escolha.py`

**Como você mediu se funciona?**
Conjunto de avaliação com gabarito e o comando `avaliar`. Três números: acertos, revisões e erros calados. O erro calado é o que importa: código errado que entra no total sem ninguém conferir. Revisão custa tempo de uma pessoa, erro calado custa dinheiro. Toda mudança de prompt ou limiar eu rodo antes e depois. As regras sozinhas deram 73% de acerto com 1 erro calado na tabela de exemplo.

**Full-text, trigrama e embeddings: quando cada um?**
Full-text (tsvector/tsquery) quebra em palavras, tira acento e reduz ao radical: bom para "tijolos" achar "tijolo", ruim para erro de digitação. Trigrama compara pedaços de 3 letras: tolera "cimeto", mas não entende língua. Embeddings comparam significado: acham sinônimos ("ferro" e "aço"), mas custam uma chamada por texto e precisam de outro índice (pgvector). Aqui, a IA da extração já troca o apelido pelo termo técnico antes da busca, então full-text + trigrama bastam.

**Por que trocar `&` por `|` no tsquery?**
`plainto_tsquery` exige todas as palavras (E). Uma linha de obra tem palavras que não existem na descrição ("saco", "cp2"), e a busca voltaria vazia. Com OU, qualquer palavra conta, e a ordenação pela nota põe os melhores em cima.

**O que é structured outputs e por que ainda usar Pydantic?**
A API garante que a resposta segue o JSON Schema (tipos e campos). O Pydantic valida regras que o esquema não expressa bem, como quantidade maior que zero. Se falhar, o item vai para revisão.

**Como funciona o cache e quando ele invalida?**
A chave é um hash de tipo da chamada + modelo + versão do prompt + entrada normalizada. A versão do prompt é um hash do arquivo do prompt: mudou o texto, mudou a chave. Resposta inválida não é guardada, para não repetir o erro. → `cache.py`

**Por que 1500 tijolos viram 1,5?**
O SINAPI vende bloco cerâmico por milheiro (MIL). O sistema converte UN para MIL antes de multiplicar. Só converte o que é matemática pura (UN ↔ MIL, KG ↔ T). Saco para kg não: existe saco de 20, 25, 40 e 50 kg.

**Como a importação é idempotente?**
Numa transação: apaga o mês/UF e insere de novo com `COPY`. Se der erro no meio, nada muda. Reimportar o mesmo mês não duplica. Planilha vazia dá erro antes de apagar.

**Como você testa código que depende de IA?**
Separando o que é meu do que é do modelo. Com um cliente falso, testo o que acontece quando a IA responde certo, recusa, corta o JSON, inventa um código ou devolve formato errado. A qualidade da IA em si eu meço com o conjunto de avaliação, não com teste unitário.

**Quanto custa?**
Duas chamadas curtas por linha nova no Haiku, com `effort` baixo. Linhas repetidas saem do cache. Em listas de obra, que repetem muito ("cimento", "areia"), o cache derruba o custo.

## 3. Perguntas de negócio

- **Quanto tempo economiza?** Use o seu número real da construtora: quanto tempo leva um orçamento de reforma hoje e quanto tempo leva revisar só os itens marcados.
- **Qual o risco?** Erro calado. Por isso a métrica principal é essa, e não o acerto.
- **E se a Caixa mudar a planilha?** O importador acha o cabeçalho e o mapeamento de colunas fica num lugar só. O teste com a planilha de exemplo quebra se o layout sair do esperado.

## 4. Para treinar em voz alta

1. Siga "10 sacos cimento cp2" pelo fluxo inteiro e explique por que ela vai para revisão.
2. Explique a diferença entre revisão e erro calado para um diretor de obra.
3. Substitua 5 linhas do gabarito por linhas reais suas, rode `avaliar` e explique o resultado.
