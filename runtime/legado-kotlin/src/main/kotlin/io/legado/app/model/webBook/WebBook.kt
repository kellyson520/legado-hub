package io.legado.app.model.webBook

import io.legado.app.data.entities.Book
import io.legado.app.data.entities.BookSource

object WebBook {
    suspend fun preciseSearchAwait(source: BookSource, name: String, author: String): Result<Book> =
        Result.failure(UnsupportedOperationException("headless preciseSearch is provided by Python bridge"))

    suspend fun getBookInfoAwait(source: BookSource, book: Book, useCache: Boolean): Book = book
}
