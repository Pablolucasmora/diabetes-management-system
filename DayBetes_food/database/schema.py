class DBSchema:
    
    usuario = """
    CREATE TABLE IF NOT EXISTS usuario (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(255),
        correo VARCHAR(255) UNIQUE NOT NULL,
        clave TEXT NOT NULL,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        categoria VARCHAR(255) CHECK (categoria IN ('admin', 'common'))
    );
    """

    catalogo = """
    CREATE TABLE IF NOT EXISTS catalogo (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
        nombre VARCHAR(255) NOT NULL UNIQUE, -- Nombre del producto
        marca VARCHAR(255), --Nombre de la marca 
        categoria VARCHAR(100) NOT NULL CHECK (categoria IN ('carne', 'pescado', 'lácteos', 'huevos', 'charcutería', 'legumbres', 'tubérculos', 'frutos secos', 'verduras', 'frutas', 'cereales', 'aceites y grasas', 'dulces', 'bebidas', 'salsas', 'condimentos', 'suplementos')),
        subtipo VARCHAR(100) NOT NULL, -- Categoria mas concreta del alimento (ejemplo: yogurt, leche, galleta, pavo, boniato, aguacate...). Esta variable servira tambien para en un futuro poder estimar macros en funcion de comidas de este mismo subtipo de la cual tenemos la informacion nutricional.
        estado_inicial VARCHAR(50) CHECK (estado_inicial IN ('solido', 'triturado/cremoso', 'liquido', 'gel')), 
        
        nutriscore VARCHAR(1) CHECK (nutriscore IN ('A', 'B', 'C', 'D', 'E')),
        NOVA INTEGER CHECK (NOVA BETWEEN 1 AND 4),
        yuka INTEGER CHECK (yuka BETWEEN 0 AND 100),
        
        porcion_default INTEGER DEFAULT 100, -- Porcion default del alimento, que después será usada como cantidad default añadida al carrito cuando no se especifique otra cosa
        
        calorias_100g REAL,
        hidratos_100g REAL,
        azucares_100g REAL,
        grasas_100g REAL,
        saturadas_100g REAL,
        proteinas_100g REAL,
        fibra_100g REAL,
        
        cafeina REAL,
        alcohol REAL,
        
        cod_barras VARCHAR,
        factor_cocinado REAL DEFAULT 1.0, -- Factor de cocinado, por si fuera necesario en algun momento usarlo para calcular el peso real

        favorito BOOLEAN DEFAULT FALSE -- para determinar los favoritos del usuario, para que le sea mas facil.
        
    );
    """

    ingesta_manual = """
    CREATE TABLE IF NOT EXISTS ingesta_manual ( --Tabla usada para cuando tomamos platos ya preparados fuera , de los cuales no sabemos exactamente las características nutricionales
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        nombre VARCHAR(255) NOT NULL, -- Nombre de esta comida manual, como puede ser tarta de la cafeteria de la uni, cocido de mi abuela, 
        descripcion TEXT, -- Descripcion del plato (Opcional), que servirá para determinar de manera mas precisa la información nutricional de los platos si meto una IA
        subtipo VARCHAR(100) NOT NULL, --Categoria mas concreta del producto, es lo mismo que en el caso de catalogo. Esta variable servira tambien para en un futuro poder estimar macros en funcion de comidas de este mismo subtipo de la cual tenemos la informacion nutricional.
        procedencia VARCHAR(255), --De donde viene, es decir, abuela, burger king, saona, big twins, subway... (para luego poder reusar en caso de que vaya a dichos lugares), estas comidas deben poderse actualizar cada vez que consuma en este sitio en caso de que haya cambiado.
        
        cantidad_g REAL NOT NULL,
        calorias_100g REAL,
        hidratos_100g REAL,
        azucares_100g REAL,
        grasas_100g REAL,
        saturadas_100g REAL,
        proteinas_100g REAL,
        fibra_100g REAL,
        
        cafeina REAL,
        alcohol REAL,
        
        indice_glucemico VARCHAR(20) CHECK (indice_glucemico IN ('alto', 'medio', 'bajo')), -- Estimación del indice glucémico de una comida
        confianza_ig INTEGER CHECK (confianza_ig BETWEEN 1 AND 5), -- Confianza con la cual establecemos el valor anterior.
        favorito BOOLEAN DEFAULT FALSE, -- Lo mismo que en catalogo

        UNIQUE (created_by, nombre)
    );
    """

    nevera = """
    CREATE TABLE IF NOT EXISTS nevera (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        nombre_tupper VARCHAR(255), -- Nombre que le pongo al tupper, como Carrillera Lunes
        fecha_entrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        es_compuesto BOOLEAN DEFAULT FALSE, -- Si tiene o no mas de un ingrediente.
        peso_total_tupper REAL -- Para hacer el display en la pagina de la nevera
    );
    """

    etiquetas = """
    CREATE TABLE IF NOT EXISTS etiquetas (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100) UNIQUE NOT NULL, -- Nombre de la etiqueta, del tipo, bajo grasa, alto proteinas...
        descripcion TEXT -- Descripcion de lo que significa
    );
    """

    recetas = """
    CREATE TABLE IF NOT EXISTS recetas (
        id SERIAL PRIMARY KEY, 
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        tipo_comida VARCHAR(50) CHECK (tipo_comida IN ('desayuno', 'almuerzo', 'comida', 'merienda', 'cena', 'snack', 'rescate')), -- Para poner este valor de default en evento_ingesta, para que sea mas facil de reusar.
        nombre VARCHAR(255) NOT NULL,
        notas TEXT,

        favorito BOOLEAN DEFAULT FALSE

    );
    """

    etiquetas_vinculadas = """
    CREATE TABLE IF NOT EXISTS etiquetas_vinculadas (
        id SERIAL PRIMARY KEY,
        etiqueta_id INTEGER REFERENCES etiquetas(id) ON DELETE CASCADE,
        
        catalogo_id INTEGER REFERENCES catalogo(id) ON DELETE CASCADE,
        receta_id INTEGER REFERENCES recetas(id) ON DELETE CASCADE,
        ingesta_manual_id INTEGER REFERENCES ingesta_manual(id) ON DELETE CASCADE,
        
        -- Función de Postgres para contar cuántos de estos campos no son nulos.
        -- Garantiza que la etiqueta se asigne a una y solo una entidad.
        CHECK (num_nonnulls(catalogo_id, receta_id, ingesta_manual_id) = 1)
    );
    """

    evento_ingesta = """
    CREATE TABLE IF NOT EXISTS evento_ingesta (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        
        estado VARCHAR(20) NOT NULL CHECK (estado IN ('planificado', 'consumido')), -- Para determinar si estoy en el carrito, o ya he consumido de manera definitiva esta comida.
        tipo_comida VARCHAR(50) CHECK (tipo_comida IN ('desayuno', 'almuerzo', 'comida', 'merienda', 'cena', 'snack', 'rescate')), -- Esto se debe de poder modificar estando ya en el carrito, por si lo añado tarde o lo quiero corregir
        nombre VARCHAR(255), -- Nombre de esta comida, por si tengo mas de un carrito y quiero definir a que se refiere cada uno. Esto se debe ajustar al principio , aunque tendrá un default tipo Comida 1, Comida 2... (estaria bien que en funcion de la hora pusiera como default Comida 1 o Almuerzo 1... y que se pudieran ajustar estos intervalos desde ajustes), pero se debera poder cambiar despues. Ademas al añadir un producto nuevo , si tengo mas de un evento_ingesta, pues me dara a elegir en donde lo quiero meter.
        
        hora_comida TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- De default sera el momento en que se añade, pero debe de ser facil de cambiar dentro del carrito.
        comida_fuera BOOLEAN DEFAULT FALSE, -- Si como o no fuera, si la mayoria de los alimentos son del catalogo, si se ha añadido desde Receta o nevera, pues el default debe de ser False, en cambio si viene la mayoria o solo de ingesta_manual debe de ser default True.
        dosis_insulina BOOLEAN DEFAULT TRUE, -- Esto debe de ser default True en caso de que la cantidad de hidratos totales sean mas de 10 , y false de default si son menos, pero luego se debe de poder ajustar en carrito.
        
        cantidad_total REAL, -- Calculada automaticamente en funcion de la suma de la cantidad plato de todas las porciones_detalle
        cantidad_ingerida REAL, -- Posteriormente de comer, antes de confirmar la comida se debe de poner la cantidad total ingerida (o en gramos o en porcentaje aproximado), para que luego se calcule automaticamente lo que ha sobrado (cantidad_total - cantidad_ingerida), y se añada automaticamente a la nevera la parte proporcional de cada ingrediente de la comida, es decir, calculamos factor de porcentaje de sobra, y lo multiplicamos sobre la cantidad de cada ingrediente, y esto se guarda en nevera de manera automatica para poderlo reusar despues.
        
        confianza_cantidad REAL CHECK (confianza_cantidad >= 0 AND confianza_cantidad <= 1), -- Suma ponderada con respecto de la cantidad de un alimento, y si es pesado o no, es decir si hay dos alimentos en un evento de ingesta en el cual uno es pesado estricto y otro no, pues sera en funcion de las cantidades de cada alimento la suma ponderada ((cant1*es_pesado_estricto + cant2*es_pesado_estricto)/cantTotal)
        confianza_calidad REAL CHECK (confianza_calidad >= 0 AND confianza_calidad <= 1), -- valor entre 0 y 1 que dice como de seguro esta uno de la informacion nutricional. Es igual que confianza_cantidad,  pero con las calidad_macro de cada ingrediente
        
        incertidumbre_hidratos REAL CHECK (incertidumbre_hidratos >= 0 AND incertidumbre_hidratos <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        incertidumbre_azucares REAL CHECK (incertidumbre_azucares >= 0 AND incertidumbre_azucares <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        incertidumbre_grasas REAL CHECK (incertidumbre_grasas >= 0 AND incertidumbre_grasas <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        incertidumbre_saturadas REAL CHECK (incertidumbre_saturadas >= 0 AND incertidumbre_saturadas <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        incertidumbre_proteinas REAL CHECK (incertidumbre_proteinas >= 0 AND incertidumbre_proteinas <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        incertidumbre_fibra REAL CHECK (incertidumbre_fibra >= 0 AND incertidumbre_fibra <= 1), -- Este valor se calcula de manera automatica, haciendo una suma ponderada de la cantidad de este macro en cada ingrediente (puede ser un valor o None) con su cantidad total , para saber la fiabilidad del valor de este macro en el recuento total (ya que none no es lo mismo que 0)
        
        notas TEXT
    );
    """

    porcion_detalle = """
    CREATE TABLE IF NOT EXISTS porcion_detalle (
        id SERIAL PRIMARY KEY,
        
        -- ARCO 1: Origen
        catalogo_id INTEGER REFERENCES catalogo(id) ON DELETE RESTRICT,
        ingesta_manual_id INTEGER REFERENCES ingesta_manual(id) ON DELETE RESTRICT,
        CHECK (num_nonnulls(catalogo_id, ingesta_manual_id) = 1),
        
        -- ARCO 2: Destino
        evento_ingesta_id INTEGER REFERENCES evento_ingesta(id) ON DELETE CASCADE,
        nevera_id INTEGER REFERENCES nevera(id) ON DELETE CASCADE,
        receta_id INTEGER REFERENCES recetas(id) ON DELETE CASCADE,
        CHECK (num_nonnulls(evento_ingesta_id, nevera_id, receta_id) = 1),
        
        cantidad_g REAL NOT NULL, -- Esta es la cantidad cocinada de un alimento, es decir, yo puedo hacer 400 gramos de quinoa, pero luego solo ponerme en el plato 100, y guardarme el resto. Por lo que despues compararemos esta cantidad con la del plato, y si es mayor , pues se guardará automaticamente en la nevera la diferencia, con el id del alimento. Para poder reusar de manera facil y rapida.
        cocinado VARCHAR(50), -- El modo de cocinado, para evaluar su efecto sobre los niveles de azucar. (puede ser: vapor, hervido-al dente, hervido-pasado, frito, crudo, horno, airfrier, tostadora, plancha), de default será plancha
        conservacion VARCHAR(50), -- Modo de conservacion: congelador, nevera, recién hecho, precocinado
        estado_final VARCHAR(50), -- Entre estas clases 'solido', 'triturado/cremoso', 'liquido', 'gel', por si se ha cambiado el estado con respecto al inicial.
        pesado_estricto BOOLEAN, -- En funcion de si hemos pesado o no el alimento antes de consumirlo
        calidad_macros BOOLEAN, -- En funcion de si hemos estimado los macros, o los hemos visto en la etiqueta
        
        cantidad_plato REAL, -- Esta es la cantidad que hemos puesto en el plato, de default sera el mismo valor que la cantidad de antes.
        es_peso_cocinado BOOLEAN DEFAULT FALSE, -- Y esto es por si hemos pesado el alimento, pero ya esta cocinado, entonces nos basaremos en su factor de cocinado, para calcular el peso real en crudo, y asi obtener bien los macros.
        offset_minutos INTEGER --Solo para evento_ingesta. se ajusta cuando esta en proceso de planificacion (no cuando se añade al carrito), y de default es la diferencia entre el timestamp en el momento del evento ingesta y el momento en que se añade este alimento al carrito en minutos 

        CHECK (offset_minutos IS NULL OR evento_ingesta_id IS NOT NULL)
    );
    """