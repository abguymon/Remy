import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { recipeApi } from '../api/client'
import { Search, ChefHat, Check, ShoppingCart, Loader2 } from 'lucide-react'

interface RecipeOption {
  name: string
  source: string
  url?: string
  image_url?: string
  slug?: string
}

interface PlanState {
  recipe_options: RecipeOption[]
  pending_cart: Array<{ name: string; quantity?: number; unit?: string }>
  messages: string[]
}

export default function Home() {
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedRecipes, setSelectedRecipes] = useState<RecipeOption[]>([])

  // Get current plan state
  const { data: planState, isLoading: loadingPlan } = useQuery<PlanState>({
    queryKey: ['planState'],
    queryFn: recipeApi.getPlanState,
    refetchOnWindowFocus: false,
  })

  // Start plan mutation
  const startPlan = useMutation({
    mutationFn: (message: string) => recipeApi.startPlan(message),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planState'] })
      setSelectedRecipes([])
    },
  })

  // Select recipes mutation
  const selectRecipes = useMutation({
    mutationFn: (recipes: RecipeOption[]) => recipeApi.selectRecipes(recipes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planState'] })
    },
  })

  // Approve cart mutation
  const approveCart = useMutation({
    mutationFn: (items: unknown[]) => recipeApi.approveCart(items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planState'] })
      queryClient.invalidateQueries({ queryKey: ['cart'] })
    },
  })

  // Reset plan mutation
  const resetPlan = useMutation({
    mutationFn: recipeApi.resetPlan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['planState'] })
      setSelectedRecipes([])
      setSearchQuery('')
    },
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (!searchQuery.trim()) return
    startPlan.mutate(searchQuery)
  }

  const toggleRecipeSelection = (recipe: RecipeOption) => {
    setSelectedRecipes((prev) => {
      const isSelected = prev.some((r) => r.name === recipe.name && r.source === recipe.source)
      if (isSelected) {
        return prev.filter((r) => !(r.name === recipe.name && r.source === recipe.source))
      }
      return [...prev, recipe]
    })
  }

  const handleSelectRecipes = () => {
    if (selectedRecipes.length === 0) return
    selectRecipes.mutate(selectedRecipes)
  }

  const handleApproveCart = () => {
    if (!planState?.pending_cart) return
    approveCart.mutate(planState.pending_cart)
  }

  const recipeOptions = planState?.recipe_options || []
  const pendingCart = planState?.pending_cart || []
  const messages = planState?.messages || []

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">What would you like to cook?</h1>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="e.g., Chicken Tikka Masala, Pasta Carbonara..."
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={startPlan.isPending || !searchQuery.trim()}
            className="px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {startPlan.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <ChefHat className="w-5 h-5" />}
            Search
          </button>
        </div>
      </form>

      {/* Messages */}
      {messages.length > 0 && (
        <div className="mb-6 p-4 bg-blue-50 text-blue-800 rounded-lg">
          {messages[messages.length - 1]}
        </div>
      )}

      {/* Recipe Options */}
      {recipeOptions.length > 0 && pendingCart.length === 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Select Recipes</h2>
            {selectedRecipes.length > 0 && (
              <button
                onClick={handleSelectRecipes}
                disabled={selectRecipes.isPending}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors flex items-center gap-2"
              >
                {selectRecipes.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Use Selected ({selectedRecipes.length})
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {recipeOptions.map((recipe, i) => {
              const isSelected = selectedRecipes.some(
                (r) => r.name === recipe.name && r.source === recipe.source
              )
              return (
                <button
                  key={`${recipe.name}-${i}`}
                  onClick={() => toggleRecipeSelection(recipe)}
                  className={`p-4 border rounded-lg text-left transition-all ${
                    isSelected
                      ? 'border-primary-500 bg-primary-50 ring-2 ring-primary-500'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex gap-4">
                    {recipe.image_url && (
                      <img
                        src={recipe.image_url}
                        alt={recipe.name}
                        className="w-20 h-20 object-cover rounded-lg"
                      />
                    )}
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900">{recipe.name}</h3>
                      <p className="text-sm text-gray-500 capitalize">{recipe.source}</p>
                    </div>
                    {isSelected && (
                      <Check className="w-5 h-5 text-primary-600 flex-shrink-0" />
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Pending Cart */}
      {pendingCart.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Shopping List ({pendingCart.length} items)
            </h2>
            <button
              onClick={handleApproveCart}
              disabled={approveCart.isPending}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              {approveCart.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <ShoppingCart className="w-4 h-4" />
              )}
              Add to Cart
            </button>
          </div>

          <div className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-100">
            {pendingCart.map((item, i) => (
              <div key={i} className="p-3 flex items-center justify-between">
                <span className="text-gray-900">{item.name}</span>
                {item.quantity && (
                  <span className="text-sm text-gray-500">
                    {item.quantity} {item.unit}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reset Button */}
      {(recipeOptions.length > 0 || pendingCart.length > 0) && (
        <button
          onClick={() => resetPlan.mutate()}
          disabled={resetPlan.isPending}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Start over
        </button>
      )}

      {/* Loading State */}
      {loadingPlan && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      )}
    </div>
  )
}
