<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Success banner -->
      <div v-if="successMessage" class="success-banner">
        {{ successMessage }}
      </div>

      <!-- Budget slider card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-controls">
          <div class="budget-display">{{ formatCurrency(budget) }}</div>
          <input
            type="range"
            class="budget-slider"
            :min="0"
            :max="maxBudget"
            :step="1000"
            v-model.number="budget"
          />
          <div class="budget-range-labels">
            <span>{{ formatCurrency(0) }}</span>
            <span>{{ formatCurrency(maxBudget) }}</span>
          </div>
        </div>
      </div>

      <!-- Stats grid -->
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ selectedItems.length }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ formatCurrency(totalCost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(remainingBudget) }}</div>
        </div>
      </div>

      <!-- Recommended items card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
        </div>

        <div v-if="selectedItems.length === 0" class="no-recommendations">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.onHand') }}</th>
                <th>{{ t('restocking.table.reorderPoint') }}</th>
                <th>{{ t('restocking.table.orderQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in selectedItems" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>
                  {{ translateProductName(item.name) }}
                  <span v-if="item.belowReorder" class="badge danger below-reorder-badge">
                    {{ t('restocking.belowReorder') }}
                  </span>
                </td>
                <td>{{ item.onHand }}</td>
                <td>{{ item.reorderPoint }}</td>
                <td><strong>{{ item.gap }}</strong></td>
                <td>{{ formatCurrency(item.unitCost) }}</td>
                <td><strong>{{ formatCurrency(item.lineCost) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Place Order button -->
        <div class="place-order-section">
          <button
            class="place-order-btn"
            :disabled="selectedItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()
    const { selectedPeriod, selectedLocation, selectedCategory, selectedStatus, getCurrentFilters } = useFilters()

    // Wrap the util so the active currency is read in setup context (refs auto-unwrap in templates,
    // so currentCurrency.value is undefined there — see Spending.vue for the same pattern)
    const formatCurrency = (value) => formatCurrencyUtil(value, currentCurrency.value)

    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const successMessage = ref(null)

    const allForecasts = ref([])
    const inventoryItems = ref([])

    // budget ref — initialised to 0 until data loads
    const budget = ref(0)
    // Guard to ensure auto-init only happens once per data load
    const budgetInitialised = ref(false)

    const candidates = computed(() => {
      const invMap = {}
      for (const inv of inventoryItems.value) {
        invMap[inv.sku] = inv
      }

      const result = []
      for (const forecast of allForecasts.value) {
        const inv = invMap[forecast.item_sku]
        if (!inv) continue

        const gap = Math.max(0, forecast.forecasted_demand - inv.quantity_on_hand)
        if (gap === 0) continue

        const belowReorder = inv.quantity_on_hand < inv.reorder_point
        const lineCost = gap * inv.unit_cost

        result.push({
          sku: inv.sku,
          name: inv.name,
          onHand: inv.quantity_on_hand,
          reorderPoint: inv.reorder_point,
          gap,
          unitCost: inv.unit_cost,
          lineCost,
          belowReorder
        })
      }

      // Sort: belowReorder first, then by gap descending
      result.sort((a, b) => {
        if (a.belowReorder !== b.belowReorder) return a.belowReorder ? -1 : 1
        return b.gap - a.gap
      })

      return result
    })

    const maxBudget = computed(() => {
      const total = candidates.value.reduce((sum, c) => sum + c.lineCost, 0)
      if (total === 0) return 100000
      return Math.ceil(total / 1000) * 1000
    })

    const selectedItems = computed(() => {
      let remaining = budget.value
      const result = []
      for (const candidate of candidates.value) {
        if (candidate.lineCost <= remaining) {
          result.push(candidate)
          remaining -= candidate.lineCost
        }
        // Skip-and-continue: don't break, keep checking cheaper items
      }
      return result
    })

    const totalCost = computed(() => selectedItems.value.reduce((sum, i) => sum + i.lineCost, 0))
    const remainingBudget = computed(() => budget.value - totalCost.value)

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        successMessage.value = null
        budgetInitialised.value = false

        const filters = getCurrentFilters()
        const [forecastsData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory({ warehouse: filters.warehouse, category: filters.category })
        ])

        allForecasts.value = forecastsData
        inventoryItems.value = inventoryData
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    // Auto-initialise budget to ~50% of maxBudget once after each data load
    watch(maxBudget, (newMax) => {
      if (!budgetInitialised.value && newMax > 0) {
        budget.value = Math.round(newMax * 0.5 / 1000) * 1000
        budgetInitialised.value = true
      }
    })

    watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], () => {
      loadData()
    })

    const placeOrder = async () => {
      if (selectedItems.value.length === 0 || submitting.value) return
      submitting.value = true
      error.value = null
      successMessage.value = null
      try {
        const items = selectedItems.value.map(i => ({
          sku: i.sku,
          name: i.name,
          quantity: i.gap,
          unit_price: i.unitCost
        }))
        const result = await api.createOrder({ items })
        successMessage.value = t('restocking.orderPlaced', { orderNumber: result.order_number })
        // Bump budget to 0 so the user must adjust before placing again
        budget.value = 0
        budgetInitialised.value = true
      } catch (err) {
        error.value = 'Failed to place order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      t,
      currentCurrency,
      translateProductName,
      formatCurrency,
      loading,
      error,
      submitting,
      successMessage,
      budget,
      maxBudget,
      candidates,
      selectedItems,
      totalCost,
      remainingBudget,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-controls {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.budget-display {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  height: 6px;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.no-recommendations {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.below-reorder-badge {
  margin-left: 0.5rem;
  vertical-align: middle;
}

.place-order-section {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.place-order-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.place-order-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 1rem 1.25rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
  font-weight: 500;
}
</style>
