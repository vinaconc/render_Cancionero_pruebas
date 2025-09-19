def procesar_linea_con_acordes_y_indices(linea, acordes, titulo_cancion, simbolo='#', es_seccion_n=False):
    resultado = ''
    idx_acorde = 0
    palabras = linea.strip().split()
    for palabra in palabras:
        es_indexada = palabra.startswith(simbolo)
        index_real = None
        if es_indexada and '=' in palabra:
            base, index_real = palabra[1:].split('=', 1)
        else:
            base = palabra[1:] if es_indexada else palabra
        if base == '_':
            if idx_acorde < len(acordes):
                resultado += f"\\raisebox{{1.7ex}}{{\\[{acordes[idx_acorde]}]}} "
                idx_acorde += 1
            else:
                resultado += '_ '
            continue
        if '_' in base:
            # Aquí base tiene acordes embebidos
            partes = base.split('_')
            latex = ''
            for i, parte in enumerate(partes):
                if i > 0 and idx_acorde < len(acordes):
                    latex += f"\\[{acordes[idx_acorde]}]"
                    idx_acorde += 1
                latex += parte
            palabra_para_indice = limpiar_para_indice(index_real if index_real else ''.join(partes))
            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                titulo_indexado = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo_cancion.strip()) if titulo_cancion else "Sin título"
                indice_tematica_global[palabra_para_indice].add(titulo_indexado)
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{latex}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += latex + ' '
        else:
            palabra_para_indice = limpiar_para_indice(index_real if index_real else base)
            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                indice_tematica_global[palabra_para_indice].add(titulo_cancion or "Sin título")
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{base}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += base + ' '
    return resultado.strip()
