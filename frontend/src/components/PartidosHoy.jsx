import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { slugify } from '../utils/slugify'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY
const supabase = createClient(supabaseUrl, supabaseKey)

const CATEGORIAS = {
  1: 'PRIMERA',
  2: 'SÉPTIMA',
  3: 'OCTAVA',
  4: 'NOVENA',
  5: 'DÉCIMA',
}

const CATEGORIAS_ROUTES = {
  1: '/primera',
  2: '/septima',
  3: '/octava',
  4: '/novena',
  5: '/decima',
}

function getEscudoPath(nombre) {
  if (!nombre) return '/escudos/argentino.png'
  const mapa = {
    'argentino': '/escudos/argentino.png',
    'atl. pasteur': '/escudos/atl.pasteur.png',
    'atl. roberts': '/escudos/atl.roberts.png',
    'ca. pintense': '/escudos/ca.pintense.png',
    'c a pintense': '/escudos/ca.pintense.png',
    'ca pintense': '/escudos/ca.pintense.png',
    'pintense': '/escudos/ca.pintense.png',
    'caset': '/escudos/caset.png',
    'dep. arenaza': '/escudos/dep.arenaza.png',
    'dep. gral pinto': '/escudos/dep.pinto.png',
    'dep gral pinto': '/escudos/dep.pinto.png',
    'el linqueño': '/escudos/el.linqueño.png',
    'juventud-unida': '/escudos/juventud.unida.png',
    'juventudunida': '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    'cael': '/escudos/el.linqueño.png',
  }
  const key = nombre.toLowerCase().trim()
  return mapa[key] || '/escudos/argentino.png'
}