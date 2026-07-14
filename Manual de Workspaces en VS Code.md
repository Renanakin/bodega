# **Arquitectura y gestión avanzada de espacios de trabajo en Visual Studio Code: Manual integral de configuración, optimización y seguridad**

El ecosistema de desarrollo moderno exige una flexibilidad sin precedentes en la organización de proyectos, la gestión de dependencias y la seguridad del entorno de ejecución. Visual Studio Code ha respondido a estas demandas mediante la implementación del concepto de "espacio de trabajo" (workspace), una abstracción que trasciende la mera apertura de carpetas en un sistema de archivos para convertirse en un contenedor lógico de metadatos, configuraciones y políticas de seguridad.1 A diferencia de los entornos de desarrollo integrados tradicionales que imponen estructuras rígidas como "soluciones" o "proyectos", el espacio de trabajo en este entorno se define como una colección de una o más carpetas abiertas simultáneamente en una única ventana de la aplicación.1 Esta arquitectura permite a los profesionales del software orquestar flujos de trabajo complejos que involucran múltiples repositorios, microservicios o subproyectos de un monorepo, manteniendo una coherencia operativa total.3

## **Fundamentos conceptuales y ontología del espacio de trabajo**

Para comprender el funcionamiento interno del entorno, es imperativo distinguir entre los diferentes estados de operación que el editor puede asumir. Un espacio de trabajo no es simplemente una referencia a una ubicación en el disco duro, sino la suma del estado de la interfaz de usuario, las configuraciones específicas del proyecto y las reglas de ejecución permitidas.1 El editor puede funcionar sin un espacio de trabajo definido, por ejemplo, al abrir un archivo individual desde el menú del sistema operativo. En este modo de archivo único, las capacidades del sistema se ven reducidas, aunque se mantiene la funcionalidad básica de edición de texto.1  
La transición hacia un espacio de trabajo se produce en el momento en que se abre una carpeta. El sistema comienza entonces a rastrear automáticamente la configuración, los archivos abiertos y el diseño de los paneles.1 Este estado de "carpeta única" representa el caso de uso más común, donde la raíz del proyecto funciona como el núcleo de conocimiento extra para las capacidades del editor.1 Sin embargo, la verdadera potencia del sistema emerge con los espacios de trabajo multi-raíz (multi-root), que permiten integrar carpetas físicamente disjuntas en una unidad lógica.1

| Concepto | Definición Técnica | Implicación Operativa |
| :---- | :---- | :---- |
| Carpeta abierta | Apertura directa de un directorio en el sistema de archivos.1 | Persistencia automática de estado y configuración en .vscode.1 |
| Espacio de trabajo sin título | Estado transitorio creado al añadir múltiples carpetas sin guardar un archivo de configuración.1 | Se restaura entre sesiones pero se elimina si se cierra la ventana sin guardar.1 |
| Archivo.code-workspace | Documento JSON que define las raíces y configuraciones de un espacio de trabajo persistente.1 | Permite la portabilidad de configuraciones y la gestión de proyectos complejos.1 |
| Espacio de trabajo vacío | Instancia de VS Code con un archivo de configuración pero sin carpetas raíz.1 | Útil para almacenar tareas o configuraciones de depuración globales sin visibilidad de archivos.1 |

## **Instalación e inicialización del entorno de desarrollo**

El proceso de establecimiento de un espacio de trabajo no requiere de instaladores adicionales, ya que está integrado en el núcleo del editor. La inicialización puede realizarse mediante diversos métodos que se adaptan a las preferencias del usuario o a los requisitos del flujo de trabajo automatizado.6

### **Métodos de apertura y creación mediante interfaz gráfica**

La forma más directa de iniciar un espacio de trabajo es a través del menú de archivo. Al seleccionar "Abrir carpeta", el usuario designa un directorio que VS Code tratará inmediatamente como la raíz de un proyecto.6 Para aquellos que prefieren una experiencia más visual, la página de "Bienvenida" o "Get Started" ofrece accesos directos claros para abrir carpetas existentes o crear nuevas que se conviertan automáticamente en espacios de trabajo al ser seleccionadas.6  
Cuando la necesidad evoluciona hacia un entorno multi-raíz, el procedimiento cambia ligeramente. El usuario debe utilizar la opción "Agregar carpeta al espacio de trabajo..." desde el menú de archivos. Si ya existe una carpeta abierta, esta acción transformará la instancia actual en un "Espacio de trabajo sin título".1 Para que este entorno sea persistente, es necesario utilizar la función "Guardar espacio de trabajo como...", lo que generará el archivo .code-workspace esencial para la colaboración en equipo y la reproducibilidad del entorno.7

### **Inicialización avanzada mediante línea de comandos y arrastre**

Para los desarrolladores que operan predominantemente desde terminales, el comando code ofrece flags potentes para la gestión de espacios de trabajo. Al pasar la ruta de una carpeta como argumento (p. ej., code.), se abre el directorio actual como un espacio de trabajo de carpeta única.1 El uso del flag \--add permite expandir un espacio de trabajo activo añadiendo nuevas carpetas sin necesidad de navegar por menús gráficos, ejecutando comandos como code \--add \<ruta\_carpeta\>.7  
El soporte de arrastrar y soltar (drag and drop) proporciona una alternativa ágil. Arrastrar una carpeta desde el explorador del sistema operativo hacia la barra lateral del explorador de archivos de VS Code la integrará en el espacio de trabajo actual.7 Es crucial observar que soltar una sola carpeta en la región del editor (donde se visualiza el código) cerrará el espacio de trabajo actual para abrir dicha carpeta en modo de carpeta única, mientras que soltar múltiples carpetas en esa misma zona creará instantáneamente un nuevo espacio de trabajo multi-raíz.7

## **Arquitectura del archivo de configuración del espacio de trabajo**

El archivo .code-workspace es el corazón técnico de los entornos multi-raíz. Se trata de un documento JSON que reside fuera de las carpetas del proyecto o en una ubicación centralizada, y que orquestra la relación entre los diferentes componentes del sistema.1 Su estructura permite no solo definir qué carpetas ver, sino cómo debe comportarse el editor específicamente para ese conjunto de herramientas.1

### **Anatomía del esquema JSON en.code-workspace**

Un archivo de espacio de trabajo estándar se compone de tres secciones principales: folders, settings y extensions. La sección de carpetas es un array de objetos que especifican la ruta de cada directorio raíz. Estas rutas pueden ser absolutas o, preferiblemente, relativas a la ubicación del archivo del espacio de trabajo, lo que facilita enormemente la portabilidad del entorno entre diferentes máquinas.1

JSON

{  
  "folders":,  
  "settings": {  
    "editor.formatOnSave": true,  
    "files.autoSave": "afterDelay"  
  },  
  "extensions": {  
    "recommendations": \[  
      "ms-azuretools.vscode-docker",  
      "dbaeumer.vscode-eslint"  
    \]  
  }  
}

La propiedad name dentro de la sección de carpetas es una herramienta de organización visual vital. Permite asignar alias descriptivos a carpetas que podrían tener nombres genéricos en el disco (como "src" o "build"), mejorando la navegación en el explorador de archivos.7 Además, la inclusión de configuraciones globales dentro de este archivo asegura que todos los desarrolladores que lo utilicen compartan los mismos estándares de formateo o reglas de autoguardado, mitigando fricciones en el control de versiones.7

## **Jerarquía y prioridad de la configuración del editor**

Uno de los aspectos más complejos y, a la vez, potentes de Visual Studio Code es su sistema jerárquico de configuración. El editor permite definir ajustes en múltiples niveles, desde lo global hasta lo específico de un lenguaje en una carpeta concreta.8 El principio rector es que el alcance más específico siempre tiene prioridad sobre el más general.8

### **Los niveles de alcance de configuración**

Existen cuatro niveles fundamentales de configuración que interactúan constantemente. En orden ascendente de prioridad, estos niveles son:

1. **Configuración predeterminada**: Los valores base definidos por el equipo de desarrollo de VS Code. Son de solo lectura y sirven como red de seguridad.8  
2. **Configuración de usuario**: Ajustes que se aplican globalmente a cualquier instancia de VS Code abierta por un usuario específico en su máquina.8 Son ideales para preferencias personales como el tema de color o el tamaño de la fuente.8  
3. **Configuración de espacio de trabajo (Global Workspace Settings)**: Ajustes almacenados en el archivo .code-workspace. Se aplican a todas las carpetas dentro de ese espacio de trabajo y sobrescriben la configuración de usuario.1  
4. **Configuración de carpeta (Folder Settings)**: Ajustes almacenados en el subdirectorio .vscode/settings.json de una carpeta específica. Tienen la máxima prioridad y se utilizan para definir reglas que solo afectan a ese componente del proyecto.7

| Nivel de Ajuste | Ubicación en el Disco (Ejemplos) | Uso Recomendado |
| :---- | :---- | :---- |
| Usuario (Windows) | %APPDATA%\\Code\\User\\settings.json.8 | Preferencias estéticas y atajos de teclado globales. |
| Usuario (macOS) | $HOME/Library/Application Support/Code/User/settings.json.8 | Configuración de terminal predeterminada. |
| Espacio de trabajo | proyecto.code-workspace.9 | Reglas de formateo para todo el equipo en multi-raíz. |
| Carpeta | mi-proyecto/.vscode/settings.json.8 | Rutas a binarios locales, exclusión de archivos temporales. |

### **Resolución de colisiones y ajustes no soportados**

En entornos multi-raíz, surge la posibilidad de conflictos entre configuraciones. Para mantener la estabilidad de la interfaz de usuario, VS Code aplica un filtro estricto: solo los ajustes relacionados con recursos (archivos y carpetas) pueden definirse a nivel de carpeta individual.7 Los ajustes que afectan a la arquitectura global del editor, como el nivel de zoom de la ventana o el diseño general de los paneles, se ignoran si se encuentran en un archivo .vscode/settings.json de una subcarpeta.7 Estos ajustes deben centralizarse en la configuración del espacio de trabajo global para que tengan efecto.7  
El editor proporciona herramientas visuales para identificar estas discrepancias. En el editor de configuración (Ctrl+,), los ajustes que no son válidos para el nivel actual aparecen atenuados o marcados con un icono de información, indicando al desarrollador que el valor está siendo ignorado debido a restricciones de alcance.7

## **El marco de seguridad: Workspace Trust y el Modo Restringido**

La apertura de código de fuentes desconocidas o repositorios públicos conlleva riesgos de seguridad inherentes. VS Code aborda esta problemática mediante la función "Workspace Trust", que establece una barrera entre el simple examen de archivos y la ejecución de código automatizado.2

### **La evolución de la configuración hacia la ejecución**

Históricamente, los archivos de configuración eran datos pasivos. Sin embargo, las herramientas modernas permiten que la configuración registre plugins, defina tareas que se ejecutan al abrir el editor o conecte integraciones externas automáticamente.15 En este paradigma, la configuración deja de ser "cómo se ve la herramienta" para ser "qué hace la herramienta".15 Un archivo .vscode/tasks.json malicioso podría ejecutar un binario dañino en el momento en que el usuario intenta compilar el proyecto.2

### **Operación en Modo Restringido**

Cuando se accede a un espacio de trabajo por primera vez y no se ha otorgado confianza explícita, VS Code entra en "Modo Restringido".2 En este estado, el editor prioriza la seguridad sobre la funcionalidad, aplicando las siguientes restricciones:

* **Desactivación de agentes de IA**: Herramientas como Copilot o agentes integrados se desactivan para prevenir la lectura o ejecución de código no verificado.2  
* **Bloqueo de tareas y depuración**: No se permite la ejecución de scripts definidos en el espacio de trabajo ni el inicio de sesiones de depuración, ya que ambas acciones implican la ejecución de binarios.2  
* **Restricción de extensiones**: La mayoría de las extensiones se deshabilitan o funcionan en una capacidad limitada si no han declarado explícitamente su compatibilidad con el modo restringido.2  
* **Ajustes de espacio de trabajo limitados**: Los ajustes que apuntan a ejecutables en el disco son ignorados para evitar que el editor llame accidentalmente a malware disfrazado de linter o compilador.2

### **Gestión proactiva de la confianza**

La confianza puede ser gestionada a nivel de carpeta individual o de forma jerárquica. Al confiar en una carpeta padre, el usuario otorga automáticamente confianza a todas sus subcarpetas, lo cual es una práctica recomendada para directorios de trabajo personales o corporativos conocidos.2 El editor de Workspace Trust proporciona una interfaz clara para revisar qué carpetas están actualmente en la lista blanca y permite alternar rápidamente el estado de confianza si se detecta una anomalía.2  
Es imperativo que el desarrollador no trate la solicitud de confianza como un trámite administrativo. Debe entenderse como una autorización para que el contenido de esa carpeta interactúe con el sistema operativo a través de las capacidades del editor.15 Antes de otorgar confianza a un proyecto descargado de internet, se recomienda revisar los contenidos de la carpeta .vscode en busca de definiciones de tareas inusuales o ajustes que alteren rutas de ejecutables del sistema.2

## **Ecosistema de extensiones y personalización del flujo de trabajo**

La verdadera potencia de un espacio de trabajo reside en su capacidad para personalizar el ecosistema de herramientas disponible para el desarrollador. A través de la gestión selectiva de extensiones y perfiles, es posible optimizar el consumo de recursos y la relevancia de las sugerencias del editor.1

### **Recomendaciones de extensiones para equipos de desarrollo**

El archivo extensions.json dentro de la carpeta .vscode permite a los líderes de proyecto definir un conjunto de herramientas indispensables. Cuando un nuevo miembro del equipo abre el espacio de trabajo, VS Code muestra una notificación recomendando la instalación de dichas extensiones.13 Esta práctica asegura que todos los colaboradores tengan acceso a los mismos linters, formateadores y herramientas de depuración, garantizando la uniformidad de la base de código.20

| Categoría de Extensión | Ejemplos Relevantes | Impacto en el Espacio de Trabajo |
| :---- | :---- | :---- |
| Linters y Formateadores | ESLint, Prettier, Stylelint.21 | Mantienen el estilo de código y detectan errores sintácticos en tiempo real.21 |
| Gestión de Versiones | GitLens, GitHub Pull Requests.23 | Integran anotaciones de autoría y flujo de revisión directamente en el editor.23 |
| Productividad Visual | Todo Tree, Peacock, Better Comments.24 | Organizan tareas pendientes y diferencian visualmente múltiples instancias del editor.25 |
| Inteligencia Artificial | GitHub Copilot, Tabnine, Amazon Q.21 | Proporcionan autocompletado contextual basado en los archivos del espacio de trabajo.21 |

### **Activación condicional y perfiles de usuario**

VS Code permite habilitar o deshabilitar extensiones específicamente para un espacio de trabajo abierto.1 Esta funcionalidad es crítica para mantener el rendimiento del sistema; por ejemplo, las extensiones de Java o C\# no necesitan estar activas mientras se trabaja en un proyecto ligero de Python.18 Los "Perfiles" llevan esta personalización un paso más allá, permitiendo crear configuraciones completas de UI, extensiones y atajos de teclado para diferentes roles (p. ej., un perfil para "Desarrollo Web" y otro para "Ciencia de Datos"), que se activan automáticamente al abrir las carpetas asociadas.18

## **Orquestación de flujos de trabajo: Tareas y Depuración**

La integración de procesos externos es fundamental para que un editor de texto funcione como un entorno de desarrollo profesional. Visual Studio Code utiliza los archivos tasks.json y launch.json para definir cómo se construye, prueba y ejecuta el código dentro del contexto del espacio de trabajo.27

### **Configuración y automatización mediante tasks.json**

El archivo de tareas permite integrar scripts de shell o procesos binarios directamente en el ciclo de vida del editor. VS Code es capaz de detectar automáticamente tareas comunes de sistemas como npm, Gulp, Grunt o Jake al escanear los archivos del proyecto.27 En un entorno multi-raíz, el comando "Ejecutar tarea" presenta una lista consolidada de todas las tareas disponibles en todas las carpetas raíz, diferenciándolas mediante un sufijo que indica la carpeta de origen.7  
Una configuración de tarea robusta incluye propiedades como:

* type: Define si la tarea se ejecuta en una shell o como un proceso independiente.27  
* problemMatcher: Una expresión regular que escanea la salida de la tarea para identificar errores y advertencias, poblando automáticamente el panel de "Problemas" del editor.27  
* presentation: Controla si la terminal integrada se muestra, si se limpia antes de la ejecución o si se enfoca automáticamente al iniciar el proceso.27  
* dependsOn: Permite crear flujos complejos donde una tarea de "compilación" debe ejecutarse antes de una tarea de "empaquetado".27

### **Depuración integral en entornos multi-raíz**

La depuración en espacios de trabajo que contienen múltiples carpetas es una de las características más avanzadas de la plataforma. VS Code busca archivos launch.json en todas las raíces y los combina en una única interfaz de usuario.7 Para escenarios complejos de microservicios, se pueden definir configuraciones de depuración "Compuestas" que inician múltiples sesiones simultáneamente (por ejemplo, el servidor backend y el cliente frontend) con un solo comando.3  
Si existen colisiones de nombres entre configuraciones de depuración de diferentes carpetas, el editor añade automáticamente el nombre de la carpeta al título de la configuración en el menú desplegable, garantizando que el desarrollador siempre sepa qué componente está iniciando.7 Además, la propiedad preLaunchTask permite asegurar que el código esté compilado y listo antes de que el depurador intente vincularse al proceso.27

## **Organización de proyectos a escala: Monorepos y Multi-repositorios**

La decisión entre utilizar un monorepo o una estructura de múltiples repositorios independientes tiene implicaciones directas en cómo se configuran los espacios de trabajo. VS Code ofrece herramientas para soportar ambos paradigmas, permitiendo una escalabilidad que se adapta al crecimiento de la organización.3

### **Análisis comparativo de estructuras de repositorios**

Un monorepo almacena múltiples proyectos en un único repositorio de Git, mientras que una estrategia multi-repo separa cada componente en su propio historial de versiones y permisos de acceso.3 VS Code, a través de sus espacios de trabajo multi-raíz, permite unificar estas visiones independientemente de la ubicación física o el origen del control de versiones de las carpetas.3

| Dimensión | Enfoque Monorepo | Enfoque Multi-repo |
| :---- | :---- | :---- |
| Visibilidad | Transparencia total; todo el código es accesible para búsqueda global.28 | Aislamiento; solo se cargan los componentes necesarios para la tarea actual.28 |
| CI/CD | Desafíos en el escalado de pipelines debido al tamaño del repositorio.29 | Pipelines más rápidos y específicos para cada componente.28 |
| Dependencias | Facilita la refactorización a gran escala y el uso de bibliotecas compartidas.3 | Control de versiones más estricto y desacoplado entre equipos.29 |
| Seguridad | Acceso de "todo o nada" por defecto.29 | Permisos granulares basados en el ámbito del proyecto.28 |

### **Optimización para grandes espacios de trabajo**

Cuando se opera en entornos que contienen miles de archivos o docenas de subproyectos, el rendimiento del editor puede verse afectado. Una práctica recomendada es el uso intensivo del ajuste files.exclude y search.exclude para ocultar directorios que no requieren indexación, como carpetas de dependencias (node\_modules), artefactos de construcción o cachés temporales.8  
En el contexto de herramientas de asistencia por IA, como Cline, los espacios de trabajo multi-raíz permiten realizar tareas que abarcan múltiples repositorios, como la actualización de un contrato de API en el backend y su inmediata implementación en los consumidores móviles y web alojados en carpetas raíz distintas.3 Sin embargo, el desarrollador debe ser consciente de las limitaciones actuales, como la aplicación de reglas personalizadas de la IA únicamente en la carpeta raíz primaria definida en el archivo del espacio de trabajo.3

## **Optimización de la interfaz y experiencia de usuario**

La eficiencia en el desarrollo no depende solo de la potencia de las herramientas, sino de la ergonomía de la interfaz. VS Code ofrece capacidades de personalización que permiten adaptar el espacio de trabajo a las necesidades cognitivas del programador.11

### **Gestión de la UI y navegación rápida**

La interfaz de VS Code se divide en áreas críticas que pueden ser reconfiguradas: el Editor, la Barra Lateral Primaria (donde reside el Explorador de Archivos), la Barra Lateral Secundaria, la Barra de Estado y el Panel Inferior (donde se encuentran la Terminal y los Problemas).31 En espacios de trabajo con múltiples carpetas, la Barra de Estado se convierte en un indicador vital de la salud del proyecto, mostrando el estado de Git, los errores detectados por los linters y el lenguaje activo para cada archivo.31  
El uso de la funcionalidad "Split View" permite editar archivos de diferentes carpetas raíz lado a lado, facilitando la comparación de implementaciones o la edición de archivos de configuración mientras se visualiza el código fuente.6 Además, las "Ventanas Flotantes" permiten desacoplar editores o terminales para utilizarlos en monitores secundarios, maximizando el espacio de visualización para proyectos complejos.30

### **Sintonización de IntelliSense y Retroalimentación Visual**

Un entorno de trabajo sobrecargado puede generar fatiga informativa. Los desarrolladores expertos suelen ajustar el comportamiento de IntelliSense para hacerlo menos intrusivo. Desactivar sugerencias automáticas basadas en palabras léxicas (editor.wordBasedSuggestions) y priorizar los resultados que provienen del análisis estático del código asegura que el programador reciba información relevante y no simplemente una lista de palabras encontradas en el proyecto.33  
Asimismo, herramientas como "Error Lens" mejoran la visibilidad de los diagnósticos al renderizar mensajes de error y advertencia directamente en la línea de código afectada, eliminando la necesidad de consultar constantemente el panel de problemas y reduciendo el salto de contexto.24 Este tipo de personalizaciones, guardadas a nivel de espacio de trabajo, garantizan que el entorno ayude al flujo de pensamiento del desarrollador en lugar de interrumpirlo.33

## **Referencia de comandos esenciales para la gestión de espacios de trabajo**

La Paleta de Comandos (Ctrl+Shift+P) es el acceso más rápido a las funciones avanzadas de gestión del entorno. Conocer la nomenclatura de estos comandos permite una manipulación fluida del espacio de trabajo sin retirar las manos del teclado.34

| Comando | Función y Utilidad |
| :---- | :---- |
| Workspaces: Save Workspace As... | Convierte un espacio de trabajo sin título en un archivo persistente .code-workspace.7 |
| Workspaces: Add Folder to Workspace... | Integra un nuevo directorio en el entorno actual.7 |
| Workspaces: Remove Folder from Workspace | Elimina la referencia a una carpeta sin borrar los archivos del disco.7 |
| Workspaces: Manage Workspace Trust | Abre el editor de seguridad para otorgar o retirar permisos de ejecución.2 |
| Preferences: Open Workspace Settings (JSON) | Accede directamente a la edición manual de los ajustes globales del espacio de trabajo.8 |
| File: Open Recent | Muestra un historial de carpetas y archivos de espacio de trabajo abiertos recientemente.7 |

## **Conclusiones y recomendaciones estratégicas**

La implementación efectiva de los espacios de trabajo en Visual Studio Code representa la diferencia entre un entorno de edición simple y una plataforma de desarrollo profesional escalable. Al tratar la configuración del entorno como parte integral del código fuente (Environment as Code), las organizaciones pueden asegurar que cada miembro del equipo trabaje bajo los mismos estándares de calidad y seguridad, independientemente de su ubicación geográfica o hardware subyacente.  
La adopción de espacios de trabajo multi-raíz debe ser la norma para proyectos que involucren microservicios o arquitecturas desacopladas, ya que permiten una visión unificada de sistemas que, de otro modo, requerirían múltiples ventanas del editor y una coordinación manual propensa a errores. Sin embargo, esta potencia debe ser equilibrada con una cultura de seguridad rigurosa, donde el Workspace Trust no sea un obstáculo que saltar, sino una herramienta de auditoría necesaria para proteger la integridad del sistema del desarrollador.  
En última instancia, la sintonización fina del espacio de trabajo —desde la jerarquía de configuraciones hasta la elección de extensiones recomendadas— crea un ecosistema que minimiza la fricción operativa y maximiza el tiempo dedicado a la resolución de problemas reales, consolidando a Visual Studio Code como la herramienta predominante en el panorama del desarrollo de software contemporáneo.

#### **Obras citadas**

1. What is a VS Code workspace?, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/editing/workspaces/workspaces](https://code.visualstudio.com/docs/editing/workspaces/workspaces)  
2. Workspace Trust \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/editing/workspaces/workspace-trust](https://code.visualstudio.com/docs/editing/workspaces/workspace-trust)  
3. Multi-Root Workspaces \- Cline Documentation, fecha de acceso: marzo 17, 2026, [https://docs.cline.bot/features/multiroot-workspace](https://docs.cline.bot/features/multiroot-workspace)  
4. Multi Root Workspaces in Visual Studio Code \- ISE Developer Blog, fecha de acceso: marzo 17, 2026, [https://devblogs.microsoft.com/ise/multi\_root\_workspaces\_in\_visual\_studio\_code/](https://devblogs.microsoft.com/ise/multi_root_workspaces_in_visual_studio_code/)  
5. fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/editing/workspaces/workspaces\#:\~:text=You%20don't%20have%20to,as%20you%20left%20it%20previously.](https://code.visualstudio.com/docs/editing/workspaces/workspaces#:~:text=You%20don't%20have%20to,as%20you%20left%20it%20previously.)  
6. Tutorial: Get started with Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/getstarted/getting-started](https://code.visualstudio.com/docs/getstarted/getting-started)  
7. Multi-root Workspaces \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces](https://code.visualstudio.com/docs/editing/workspaces/multi-root-workspaces)  
8. User and workspace settings \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/configure/settings](https://code.visualstudio.com/docs/configure/settings)  
9. creating-a-multi-root-workspace.md \- visual-studio-code \- GitHub, fecha de acceso: marzo 17, 2026, [https://github.com/stevekinney/stevekinney.net/blob/main/content/courses/visual-studio-code/creating-a-multi-root-workspace.md](https://github.com/stevekinney/stevekinney.net/blob/main/content/courses/visual-studio-code/creating-a-multi-root-workspace.md)  
10. Opening a Visual Studio Code workspace \- IBM, fecha de acceso: marzo 17, 2026, [https://www.ibm.com/docs/en/watsonx/watsonx-code-assistant-4z/1.x?topic=extension-opening-visual-studio-code-workspace](https://www.ibm.com/docs/en/watsonx/watsonx-code-assistant-4z/1.x?topic=extension-opening-visual-studio-code-workspace)  
11. Workspaces in VS Code and How to Set Up and Customize Them? \- Codeguage, fecha de acceso: marzo 17, 2026, [https://www.codeguage.com/blog/vscode-workspace](https://www.codeguage.com/blog/vscode-workspace)  
12. visual studio code \- How to create a workspace \- Stack Overflow, fecha de acceso: marzo 17, 2026, [https://stackoverflow.com/questions/53308870/how-to-create-a-workspace](https://stackoverflow.com/questions/53308870/how-to-create-a-workspace)  
13. Using recommended extensions and settings in VS Code \- Leonardo Faria, fecha de acceso: marzo 17, 2026, [https://leonardofaria.net/2023/02/10/using-recommended-extensions-and-settings-in-vs-code](https://leonardofaria.net/2023/02/10/using-recommended-extensions-and-settings-in-vs-code)  
14. Workspace file vs .vscode files \- where do my project settings actually go? \- Reddit, fecha de acceso: marzo 17, 2026, [https://www.reddit.com/r/vscode/comments/chn6tk/workspace\_file\_vs\_vscode\_files\_where\_do\_my/](https://www.reddit.com/r/vscode/comments/chn6tk/workspace_file_vs_vscode_files_where_do_my/)  
15. When Configuration Starts Acting Like Code: A Beginner's Guide to Workspace Trust | by Dinesh Karakambaka | Feb, 2026 | Medium, fecha de acceso: marzo 17, 2026, [https://medium.com/@kdineshkvkl/when-configuration-starts-acting-like-code-a-beginners-guide-to-workspace-trust-8ea5317c380f](https://medium.com/@kdineshkvkl/when-configuration-starts-acting-like-code-a-beginners-guide-to-workspace-trust-8ea5317c380f)  
16. Security \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/copilot/security](https://code.visualstudio.com/docs/copilot/security)  
17. vscode: Workspace Trust | Orchestra, fecha de acceso: marzo 17, 2026, [https://www.getorchestra.io/guides/vscode-workspace-trust](https://www.getorchestra.io/guides/vscode-workspace-trust)  
18. Use extensions in Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/getstarted/extensions](https://code.visualstudio.com/docs/getstarted/extensions)  
19. Extension Marketplace \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/configure/extensions/extension-marketplace](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace)  
20. VS Code tips — Workspace recommended extensions \- YouTube, fecha de acceso: marzo 17, 2026, [https://www.youtube.com/watch?v=JX-mBeri7o8](https://www.youtube.com/watch?v=JX-mBeri7o8)  
21. Top 20 VS Code Extensions to Supercharge Your Development Productivity \- Syncfusion, fecha de acceso: marzo 17, 2026, [https://www.syncfusion.com/blogs/post/top-vs-code-extensions](https://www.syncfusion.com/blogs/post/top-vs-code-extensions)  
22. 25 Best VSCode Extensions for Developers in 2025 \- Boost Productivity | early Blog \- EarlyAI, fecha de acceso: marzo 17, 2026, [https://www.startearly.ai/post/25-best-vscode-extensions-for-developers](https://www.startearly.ai/post/25-best-vscode-extensions-for-developers)  
23. Top 20 Best VScode Extensions for 2026 \- Jit.io, fecha de acceso: marzo 17, 2026, [https://www.jit.io/blog/vscode-extensions-for-2023](https://www.jit.io/blog/vscode-extensions-for-2023)  
24. 10 VS Code Extensions That Actually Save You Hours Every Week | by Navanath Jadhav, fecha de acceso: marzo 17, 2026, [https://navanathjadhav.medium.com/10-vs-code-extensions-that-actually-save-you-hours-every-week-eedb968f5c8b](https://navanathjadhav.medium.com/10-vs-code-extensions-that-actually-save-you-hours-every-week-eedb968f5c8b)  
25. Top 14 VS Code Extensions for 2026: Productivity, Testing, Security, and Collaboration, fecha de acceso: marzo 17, 2026, [https://www.aikido.dev/blog/top-vs-code-extensions](https://www.aikido.dev/blog/top-vs-code-extensions)  
26. Profiles in Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/configure/profiles](https://code.visualstudio.com/docs/configure/profiles)  
27. Integrate with External Tools via Tasks \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/editor/tasks](https://code.visualstudio.com/docs/editor/tasks)  
28. Monorepo vs. multi-repo: Different strategies for organizing repositories \- Thoughtworks, fecha de acceso: marzo 17, 2026, [https://www.thoughtworks.com/en-gb/insights/blog/agile-engineering-practices/monorepo-vs-multirepo](https://www.thoughtworks.com/en-gb/insights/blog/agile-engineering-practices/monorepo-vs-multirepo)  
29. Terraform monorepo vs. multi-repo: The great debate \- HashiCorp, fecha de acceso: marzo 17, 2026, [https://www.hashicorp.com/en/blog/terraform-mono-repo-vs-multi-repo-the-great-debate](https://www.hashicorp.com/en/blog/terraform-mono-repo-vs-multi-repo-the-great-debate)  
30. Visual Studio Code tips and tricks, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/getstarted/tips-and-tricks](https://code.visualstudio.com/docs/getstarted/tips-and-tricks)  
31. User interface \- Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://code.visualstudio.com/docs/getstarted/userinterface](https://code.visualstudio.com/docs/getstarted/userinterface)  
32. Crafting Your VSCode Workspace: Effective Customization Tips \- DEV Community, fecha de acceso: marzo 17, 2026, [https://dev.to/amatisse/crafting-your-vscode-workspace-effective-customization-tips-346i](https://dev.to/amatisse/crafting-your-vscode-workspace-effective-customization-tips-346i)  
33. I realized why I was annoyed with VSCode and here's how I fixed it \- Reddit, fecha de acceso: marzo 17, 2026, [https://www.reddit.com/r/vscode/comments/pqfpnc/i\_realized\_why\_i\_was\_annoyed\_with\_vscode\_and/](https://www.reddit.com/r/vscode/comments/pqfpnc/i_realized_why_i_was_annoyed_with_vscode_and/)  
34. Command Palette commands for the Databricks extension for Visual Studio Code, fecha de acceso: marzo 17, 2026, [https://docs.databricks.com/gcp/en/dev-tools/vscode-ext/command-palette](https://docs.databricks.com/gcp/en/dev-tools/vscode-ext/command-palette)  
35. Using the Visual Studio Code Command Palette in GitHub Codespaces, fecha de acceso: marzo 17, 2026, [https://docs.github.com/en/codespaces/reference/using-the-vs-code-command-palette-in-codespaces](https://docs.github.com/en/codespaces/reference/using-the-vs-code-command-palette-in-codespaces)