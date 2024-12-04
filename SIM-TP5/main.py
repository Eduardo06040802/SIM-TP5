import os
import random
import math
from flask import Flask, request, render_template, send_file
from enum import Enum
import pandas as pd
import io

class EstadoEquipo(Enum):
    LIBRE = "Libre"
    OCUPADO = "Ocupado"
    MANTENIMIENTO = "Mantenimiento"

class EstadoAlumno(Enum):
    SIENDO_ATENDIDO = "SA"
    EN_COLA = "EC"
    ATENCION_FINALIZADA = "AF"

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates_new'))

def integracion_euler(A0, h=0.1):
    A = A0
    t = 0
    resultados = []
    while A > 0:
        dA = (-68 - (A**2)/A0) * h
        A += dA
        t += h
        resultados.append((t, A))
        if A < 0:
            A = 0
    return resultados, t

class Simulacion:
    def __init__(self, equipos=6, inf_inscripcion=5, sup_inscripcion=8, media_llegada=2.0):
        self.equipos = [{'id': i+1, 'estado': EstadoEquipo.LIBRE, 'fin_inscripcion': None, 'fin_mantenimiento': None, 'alumno_actual': None} for i in range(equipos)]
        self.inf_inscripcion = inf_inscripcion
        self.sup_inscripcion = sup_inscripcion
        self.media_llegada = media_llegada
        self.cola = 0
        self.tiempo_actual = 0
        self.resultados = []
        self.contador_alumnos = 0
        self.estado_alumnos = {}
        self.tiempo_llegada_alumnos = {}
        self.tiempo_inicio_atencion = {}
        self.tiempos_espera = {}
        self.alumnos_en_cola = []
        self.tiempo_espera_total = 0
        self.alumnos_con_espera = 0
        self.proximo_mantenimiento = None
        self.mantenimiento_en_espera = False
        self.proxima_computadora_mantenimiento = 0
        self.h = 0.1  # Paso de integración parametrizable
        self.alumnos_que_se_van = 0
        self.total_alumnos = 0
        self.integraciones = {}

    def generar_tiempo_llegada(self):
        rnd = random.random()
        tiempo = -self.media_llegada * math.log(1 - rnd)
        return rnd, round(tiempo, 2)

    def generar_tiempo_inscripcion(self):
        rnd = random.random()
        tiempo = self.inf_inscripcion + (self.sup_inscripcion - self.inf_inscripcion) * rnd
        return rnd, round(tiempo, 2)

    def generar_tiempo_mantenimiento(self):
        A0 = random.choice([1000, 1500, 2000])
        resultados, tiempo = integracion_euler(A0, self.h)
        self.integraciones[self.tiempo_actual] = resultados
        return random.random(), round(tiempo, 2), A0

    def generar_tiempo_regreso(self):
        rnd = random.random()
        tiempo_regreso = 27 + (33 - 27) * rnd
        return rnd, round(tiempo_regreso, 2)

    def obtener_equipo_libre(self):
        for equipo in self.equipos:
            if equipo['estado'] == EstadoEquipo.LIBRE:
                return equipo
        return None

    def actualizar_estado_alumno(self, id_alumno, estado, tiempo_actual):
        if id_alumno not in self.estado_alumnos:
            self.estado_alumnos[id_alumno] = estado
            self.tiempo_llegada_alumnos[id_alumno] = tiempo_actual
            if estado == EstadoAlumno.EN_COLA:
                self.alumnos_en_cola.append(id_alumno)
                self.tiempos_espera[id_alumno] = 0
                self.alumnos_con_espera += 1
        else:
            anterior_estado = self.estado_alumnos[id_alumno]
            self.estado_alumnos[id_alumno] = estado
            if estado == EstadoAlumno.SIENDO_ATENDIDO and anterior_estado == EstadoAlumno.EN_COLA:
                self.alumnos_en_cola.remove(id_alumno)
                tiempo_espera = tiempo_actual - self.tiempo_llegada_alumnos[id_alumno]
                self.tiempos_espera[id_alumno] = tiempo_espera
                if tiempo_espera > 0:
                    self.tiempo_espera_total += tiempo_espera

    def calcular_tiempo_espera(self, id_alumno):
        if id_alumno in self.estado_alumnos:
            if self.estado_alumnos[id_alumno] == EstadoAlumno.EN_COLA:
                return round(self.tiempo_actual - self.tiempo_llegada_alumnos[id_alumno], 2)
            elif id_alumno in self.tiempos_espera:
                return round(self.tiempos_espera[id_alumno], 2)
        return 0
    
    def calcular_estadisticas(self):
        porcentaje_se_van = (self.alumnos_que_se_van / self.total_alumnos) * 100 if self.total_alumnos > 0 else 0
        tiempo_espera_promedio = self.tiempo_espera_total / self.alumnos_con_espera if self.alumnos_con_espera > 0 else 0
        return porcentaje_se_van, tiempo_espera_promedio

    def calcular_estadisticas_espera(self):
        if self.alumnos_con_espera > 0:
            acumulado = round(self.tiempo_espera_total, 2)
            promedio = round(acumulado / self.alumnos_con_espera, 2)
            return acumulado, promedio
        return 0, 0

    def agregar_estados_alumnos(self, estado_actual):
        for i in range(1, self.contador_alumnos + 1):
            id_alumno = f"A{i}"
            if id_alumno in self.estado_alumnos:
                estado_actual[f'Estado A{i}'] = self.estado_alumnos[id_alumno].value
                estado_actual[f'Tiempo Espera A{i}'] = self.calcular_tiempo_espera(id_alumno)
            else:
                estado_actual[f'Estado A{i}'] = ''
                estado_actual[f'Tiempo Espera A{i}'] = ''

    def obtener_proximo_evento(self):
        eventos = []
        eventos.append(('llegada', self.proxima_llegada))
        if self.proximo_mantenimiento:
            eventos.append(('inicio_mantenimiento', self.proximo_mantenimiento))
        for equipo in self.equipos:
            if equipo['fin_mantenimiento']:
                eventos.append(('fin_mantenimiento', equipo['fin_mantenimiento'], equipo))
            if equipo['fin_inscripcion']:
                eventos.append(('fin_inscripcion', equipo['fin_inscripcion'], equipo))
        eventos.sort(key=lambda x: x[1])
        return eventos[0]

    def simular(self, tiempo_total):
        rnd_llegada, tiempo_llegada = self.generar_tiempo_llegada()
        self.tiempo_actual = 0
        self.proxima_llegada = tiempo_llegada
        self.contador_alumnos = 1
        id_actual = f"A{self.contador_alumnos}"
        rnd_mant, tiempo_mant, A0 = self.generar_tiempo_mantenimiento()
        self.equipos[0]['estado'] = EstadoEquipo.MANTENIMIENTO
        self.equipos[0]['fin_mantenimiento'] = tiempo_mant
        self.proxima_computadora_mantenimiento = 1

        estado = {
            'Evento': 'Inicializacion',
            'Reloj': round(self.tiempo_actual, 2),
            'RND Llegada': round(rnd_llegada, 2),
            'Tiempo Llegada': round(tiempo_llegada, 2),
            'Próxima Llegada': round(self.proxima_llegada, 2),
            'Máquina': 'N/A',
            'RND Inscripción': 'N/A',
            'Tiempo Inscripción': 'N/A',
            'Fin Inscripción': 'N/A',
            'RND Mantenimiento': round(rnd_mant, 2),
            'Tiempo Mantenimiento': round(tiempo_mant, 2),
            'Fin Mantenimiento': round(tiempo_mant, 2),
            'A0': A0
        }

        for i, equipo in enumerate(self.equipos, 1):
            estado[f'Máquina {i}'] = equipo['estado'].value
        estado['Cola'] = self.cola
        self.agregar_estados_alumnos(estado)
        self.resultados.append(estado)

        while self.tiempo_actual < tiempo_total:
            evento = self.obtener_proximo_evento()
            self.tiempo_actual = evento[1]
            tipo_evento = evento[0]

            if tipo_evento == 'llegada':
                estado = self.procesar_llegada(id_actual, rnd_llegada, tiempo_llegada)
                rnd_llegada, tiempo_llegada = self.generar_tiempo_llegada()
                self.proxima_llegada = self.tiempo_actual + tiempo_llegada
                self.contador_alumnos += 1
                id_actual = f"A{self.contador_alumnos}"
            elif tipo_evento == 'inicio_mantenimiento':
                estado = self.procesar_inicio_mantenimiento()
                if estado is None:
                    continue
            elif tipo_evento == 'fin_mantenimiento':
                equipo = evento[2]
                estado = self.procesar_fin_mantenimiento(equipo)
            elif tipo_evento == 'fin_inscripcion':
                equipo = evento[2]
                estado = self.procesar_fin_inscripcion(equipo)

            if estado:
                self.resultados.append(estado)

        porcentaje_se_van = (self.alumnos_que_se_van / self.total_alumnos) * 100 if self.total_alumnos > 0 else 0
        tiempo_espera_promedio = self.tiempo_espera_total / self.alumnos_con_espera if self.alumnos_con_espera > 0 else 0
    
        for estado in self.resultados:
            estado['% Alumnos que se van'] = round(porcentaje_se_van, 2)
            estado['Tiempo espera promedio'] = round(tiempo_espera_promedio, 2)
    
        return sorted(self.resultados, key=lambda x: x['Reloj'])

    def procesar_llegada(self, id_alumno, rnd_llegada, tiempo_llegada):
        self.total_alumnos += 1
        estado = {
            'Evento': f'Llegada Alumno {id_alumno}',
            'Reloj': round(self.tiempo_actual, 2),
            'RND Llegada': round(rnd_llegada, 2),
            'Tiempo Llegada': round(tiempo_llegada, 2),
            'Próxima Llegada': round(self.proxima_llegada, 2),
            'Máquina': 'N/A',
            'RND Inscripción': 'N/A',
            'Tiempo Inscripción': 'N/A',
            'Fin Inscripción': 'N/A',
            'RND Mantenimiento': 'N/A',
            'Tiempo Mantenimiento': 'N/A',
            'Fin Mantenimiento': 'N/A'
        }

        equipo_libre = self.obtener_equipo_libre()
        if equipo_libre:
            equipo_libre['estado'] = EstadoEquipo.OCUPADO
            rnd_ins, tiempo_ins = self.generar_tiempo_inscripcion()
            equipo_libre['fin_inscripcion'] = self.tiempo_actual + tiempo_ins
            equipo_libre['alumno_actual'] = id_alumno
            estado.update({
                'Máquina': equipo_libre['id'],
                'RND Inscripción': round(rnd_ins, 2),
                'Tiempo Inscripción': round(tiempo_ins, 2),
                'Fin Inscripción': round(equipo_libre['fin_inscripcion'], 2)
            })
            self.actualizar_estado_alumno(id_alumno, EstadoAlumno.SIENDO_ATENDIDO, self.tiempo_actual)
        else:
            self.cola += 1
            if self.cola > 5:
                self.alumnos_que_se_van += 1
                rnd_regreso, tiempo_regreso = self.generar_tiempo_regreso()
                # Programar el regreso del alumno
                # ... (implementar lógica de regreso) ...
            self.actualizar_estado_alumno(id_alumno, EstadoAlumno.EN_COLA, self.tiempo_actual)

        for i, equipo in enumerate(self.equipos, 1):
            estado[f'Máquina {i}'] = equipo['estado'].value
        estado['Cola'] = self.cola
        self.agregar_estados_alumnos(estado)
        return estado

    def procesar_inicio_mantenimiento(self):
        if self.mantenimiento_en_espera:
            return None
        equipo_libre = self.obtener_equipo_libre()
        if not equipo_libre:
            self.mantenimiento_en_espera = True
            return None

        rnd_mant, tiempo_mant, A0 = self.generar_tiempo_mantenimiento()
        equipo_libre['estado'] = EstadoEquipo.MANTENIMIENTO
        equipo_libre['fin_mantenimiento'] = self.tiempo_actual + tiempo_mant
        self.proximo_mantenimiento = None
        

        estado = {
            'Evento': f'Inicio Mantenimiento M{equipo_libre["id"]}',
            'Reloj': round(self.tiempo_actual, 2),
            'RND Llegada': 'N/A',
            'Tiempo Llegada': 'N/A',
            'Próxima Llegada': round(self.proxima_llegada, 2),
            'Máquina': equipo_libre['id'],
            'RND Inscripción': 'N/A',
            'Tiempo Inscripción': 'N/A',
            'Fin Inscripción': 'N/A',
            'RND Mantenimiento': round(rnd_mant, 2),
            'Tiempo Mantenimiento': round(tiempo_mant, 2),
            'Fin Mantenimiento': round(equipo_libre['fin_mantenimiento'], 2),
            'Cola': self.cola,
            'A0': A0
        }

        for i, eq in enumerate(self.equipos, 1):
            estado[f'Máquina {i}'] = eq['estado'].value
        self.agregar_estados_alumnos(estado)
        estado['Integración'] = self.integraciones[self.tiempo_actual]
        return estado

    def procesar_fin_mantenimiento(self, equipo):
        equipo['estado'] = EstadoEquipo.LIBRE
        equipo['fin_mantenimiento'] = None

        estado = {
            'Evento': f'Fin Mantenimiento M{equipo["id"]}',
            'Reloj': round(self.tiempo_actual, 2),
            'RND Llegada': 'N/A',
            'Tiempo Llegada': 'N/A',
            'Próxima Llegada': round(self.proxima_llegada, 2),
            'Máquina': equipo['id'],
            'RND Inscripción': 'N/A',
            'Tiempo Inscripción': 'N/A',
            'Fin Inscripción': 'N/A',
            'RND Mantenimiento': 'N/A',
            'Tiempo Mantenimiento': 'N/A',
            'Fin Mantenimiento': 'N/A',
            'Cola': self.cola
        }

        if self.proxima_computadora_mantenimiento < len(self.equipos):
            siguiente_equipo = self.equipos[self.proxima_computadora_mantenimiento]
            rnd_mant, tiempo_mant, A0 = self.generar_tiempo_mantenimiento()
            siguiente_equipo['estado'] = EstadoEquipo.MANTENIMIENTO
            siguiente_equipo['fin_mantenimiento'] = self.tiempo_actual + tiempo_mant
            self.proxima_computadora_mantenimiento += 1

            """estado['Máquina'] = siguiente_equipo['id']
            estado['RND Mantenimiento'] = round(rnd_mant, 2)
            estado['Tiempo Mantenimiento'] = round(tiempo_mant, 2)
            estado['Fin Mantenimiento'] = round(siguiente_equipo['fin_mantenimiento'], 2)"""

            estado.update({
                'Máquina': siguiente_equipo['id'],
                'RND Mantenimiento': round(rnd_mant, 2),
                'Tiempo Mantenimiento': round(tiempo_mant, 2),
                'Fin Mantenimiento': round(siguiente_equipo['fin_mantenimiento'], 2),
                'A0': A0
            })
        else:
            # Se ha completado el mantenimiento de todas las computadoras
            rnd_vuelta, tiempo_vuelta = self.generar_tiempo_regreso()
            self.proximo_mantenimiento = self.tiempo_actual + tiempo_vuelta
            self.proxima_computadora_mantenimiento = 0
        
            estado.update({
                'RND Tiempo Vuelta': round(rnd_vuelta, 2),
                'Tiempo Vuelta': round(tiempo_vuelta, 2),
                'Próximo Inicio Mantenimiento': round(self.proximo_mantenimiento, 2)
            })
        
        for i, eq in enumerate(self.equipos, 1):
            estado[f'Máquina {i}'] = eq['estado'].value
        self.agregar_estados_alumnos(estado)

        # Si hay alumnos en cola, atender al siguiente
        if self.alumnos_en_cola:
            siguiente_alumno = self.alumnos_en_cola[0]
            rnd_ins, tiempo_ins = self.generar_tiempo_inscripcion()
            equipo['estado'] = EstadoEquipo.OCUPADO
            equipo['fin_inscripcion'] = self.tiempo_actual + tiempo_ins
            equipo['alumno_actual'] = siguiente_alumno
            self.actualizar_estado_alumno(siguiente_alumno, EstadoAlumno.SIENDO_ATENDIDO, self.tiempo_actual)
            self.cola -= 1

        return estado

    def procesar_fin_inscripcion(self, equipo):
        alumno_finalizado = equipo['alumno_actual']
        self.actualizar_estado_alumno(alumno_finalizado, EstadoAlumno.ATENCION_FINALIZADA, self.tiempo_actual)
        equipo['estado'] = EstadoEquipo.LIBRE
        equipo['fin_inscripcion'] = None
        equipo['alumno_actual'] = None

        # Atender siguiente alumno en cola si existe
        if self.alumnos_en_cola:
            siguiente_alumno = self.alumnos_en_cola[0]
            rnd_ins, tiempo_ins = self.generar_tiempo_inscripcion()
            equipo['estado'] = EstadoEquipo.OCUPADO
            equipo['fin_inscripcion'] = self.tiempo_actual + tiempo_ins
            equipo['alumno_actual'] = siguiente_alumno
            self.actualizar_estado_alumno(siguiente_alumno, EstadoAlumno.SIENDO_ATENDIDO, self.tiempo_actual)
            self.cola -= 1

        estado = {
            'Evento': f'Fin Inscripción {alumno_finalizado}',
            'Reloj': round(self.tiempo_actual, 2),
            'RND Llegada': 'N/A',
            'Tiempo Llegada': 'N/A',
            'Próxima Llegada': round(self.proxima_llegada, 2),
            'Máquina': equipo['id'],
            'RND Inscripción': 'N/A' if not self.alumnos_en_cola else round(rnd_ins, 2),
            'Tiempo Inscripción': 'N/A' if not self.alumnos_en_cola else round(tiempo_ins, 2),
            'Fin Inscripción': 'N/A' if not self.alumnos_en_cola else round(equipo['fin_inscripcion'], 2),
            'RND Mantenimiento': 'N/A',
            'Tiempo Mantenimiento': 'N/A',
            'Fin Mantenimiento': 'N/A',
            'Cola': self.cola
        }

        for i, eq in enumerate(self.equipos, 1):
            estado[f'Máquina {i}'] = eq['estado'].value
        self.agregar_estados_alumnos(estado)

        return estado



@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Obtener valores del formulario
        equipos = int(request.form.get('equipos', 6))
        inf_inscripcion = int(request.form.get('inf_inscripcion', 5))
        sup_inscripcion = int(request.form.get('sup_inscripcion', 8))
        media_llegada = float(request.form.get('media_llegada', 2.0))
        h = float(request.form.get('h', 0.1))
        dias_simulacion = int(request.form.get('dias_simulacion', 1))
        
        # Crear instancia de simulación con los parámetros
        sim = Simulacion(
            equipos=equipos,
            inf_inscripcion=inf_inscripcion,
            sup_inscripcion=sup_inscripcion,
            media_llegada=media_llegada
        )
        sim.h = h  # Establecer el paso de integración
        
        # Calcular tiempo total en minutos (8 horas * 60 minutos * cantidad de días)
        tiempo_total = 480 * dias_simulacion
        tabla = sim.simular(tiempo_total)
        
        if 'download' in request.form:
            df = pd.DataFrame(tabla)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Simulacion', index=False)
                for tiempo, integracion in sim.integraciones.items():
                    df_integracion = pd.DataFrame(integracion, columns=['Tiempo', 'Archivos'])
                    df_integracion.to_excel(writer, sheet_name=f'Integracion_{tiempo}', index=False)
            output.seek(0)
            return send_file(
                output,
                download_name='simulacion.xlsx',
                as_attachment=True,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        
        return render_template('nuevo_colas.html', tabla=tabla)
    return render_template('menu.html')

if __name__ == '__main__':
    app.run(debug=True)