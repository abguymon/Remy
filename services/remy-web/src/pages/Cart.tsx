import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cartApi } from '../api/client'
import { ShoppingCart, Trash2, Loader2, Package } from 'lucide-react'

interface CartItem {
  product_id: string
  name: string
  quantity: number
  price?: number
  image_url?: string
}

interface CartData {
  items: CartItem[]
  total?: number
}

export default function Cart() {
  const queryClient = useQueryClient()

  const { data: cart, isLoading } = useQuery<CartData>({
    queryKey: ['cart'],
    queryFn: cartApi.getCart,
  })

  const removeItem = useMutation({
    mutationFn: (productId: string) => cartApi.removeItem(productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cart'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    )
  }

  const items = cart?.items || []

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <ShoppingCart className="w-8 h-8 text-primary-600" />
        <h1 className="text-2xl font-bold text-gray-900">Your Cart</h1>
      </div>

      {items.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
          <Package className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">Your cart is empty</p>
          <p className="text-sm text-gray-400 mt-1">
            Search for recipes to add items to your cart
          </p>
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100 mb-6">
            {items.map((item) => (
              <div key={item.product_id} className="p-4 flex items-center gap-4">
                {item.image_url && (
                  <img
                    src={item.image_url}
                    alt={item.name}
                    className="w-16 h-16 object-cover rounded-lg"
                  />
                )}
                <div className="flex-1">
                  <h3 className="font-medium text-gray-900">{item.name}</h3>
                  <p className="text-sm text-gray-500">Qty: {item.quantity}</p>
                </div>
                {item.price && (
                  <span className="text-gray-900 font-medium">
                    ${item.price.toFixed(2)}
                  </span>
                )}
                <button
                  onClick={() => removeItem.mutate(item.product_id)}
                  disabled={removeItem.isPending}
                  className="p-2 text-gray-400 hover:text-red-500 transition-colors"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
            ))}
          </div>

          {cart?.total && (
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <span className="font-medium text-gray-900">Total</span>
              <span className="text-xl font-bold text-gray-900">
                ${cart.total.toFixed(2)}
              </span>
            </div>
          )}

          <div className="mt-6">
            <a
              href="https://www.kroger.com/cart"
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-3 px-4 bg-primary-600 text-white text-center rounded-lg hover:bg-primary-700 transition-colors"
            >
              Complete Purchase on Kroger
            </a>
          </div>
        </>
      )}
    </div>
  )
}
