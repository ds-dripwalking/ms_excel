<script setup lang="ts">
import { ref } from 'vue'

const message = ref('Welcome to Kombain!')
</script>

<template>
  <div class="container">
    <h1>{{ message }}</h1>
    <p>Kombain Frontend is running.</p>
  </div>
</template>

<style>
.container {
  font-family: Arial, sans-serif;
  text-align: center;
  padding: 50px;
}
</style>
