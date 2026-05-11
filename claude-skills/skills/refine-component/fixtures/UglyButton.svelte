<script lang="ts">
  let { label = 'Click', onclick = () => {} }: { label?: string; onclick?: () => void } = $props();
  let count = $state(0);
</script>

<button
  class="bg-blue-500 text-white px-2 py-1 rounded text-sm"
  onclick={() => { count++; onclick(); }}
>
  {label} ({count})
</button>
