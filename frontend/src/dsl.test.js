import test from 'node:test'
import assert from 'node:assert/strict'
import { getVignette, removeVignette, setVignette } from './dsl.js'

const BASE = 'LOAD "a.png"\nBLUR 3\nSAVE "b.png"\n'

test('no vignette to start with', () => {
  assert.equal(getVignette(BASE), null)
})

test('inserts before the final SAVE', () => {
  assert.equal(setVignette(BASE, 40), 'LOAD "a.png"\nBLUR 3\nVIGNETTE 40\nSAVE "b.png"\n')
})

test('appends when there is no SAVE', () => {
  assert.equal(setVignette('LOAD "a.png"', 40), 'LOAD "a.png"\nVIGNETTE 40')
})

test('updates in place instead of adding a second line', () => {
  const once = setVignette(BASE, 40)
  const twice = setVignette(once, 75)
  assert.equal(twice.match(/VIGNETTE/g).length, 1)
  assert.equal(getVignette(twice), 75)
})

test('keeps indentation and a trailing comment when updating', () => {
  const src = 'LOAD "a.png"\n  vignette 30   # soft\nSAVE "b.png"'
  assert.equal(setVignette(src, 55), 'LOAD "a.png"\n  VIGNETTE 55   # soft\nSAVE "b.png"')
})

test('reads a lowercase line', () => {
  assert.equal(getVignette('vignette 20'), 20)
})

test('does not mistake a comment for a vignette', () => {
  assert.equal(getVignette('# VIGNETTE 50\nLOAD "a.png"'), null)
})

test('removing restores the original program', () => {
  assert.equal(removeVignette(setVignette(BASE, 40)), BASE)
})

test('removing from a program without one changes nothing', () => {
  assert.equal(removeVignette(BASE), BASE)
})

test('only the last SAVE position is used when there are several lines like it', () => {
  const src = 'LOAD "a.png"\nSAVE "x.png"\nSAVE "y.png"'
  assert.equal(setVignette(src, 10), 'LOAD "a.png"\nSAVE "x.png"\nVIGNETTE 10\nSAVE "y.png"')
})
